from __future__ import annotations

import hashlib
import html
import mimetypes
import re
import shutil
import urllib.parse
from pathlib import Path

from ._commands import CommandError, run_sandboxed
from ._source import sha256_file
from .models import AssetRecord, Diagnostic, DiagnosticLevel

_ASSET_EXTENSIONS = (
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".svg",
    ".eps",
    ".ps",
)
_MARKDOWN_IMAGE = re.compile(
    r"(?P<prefix>!\[[^\]\n]*\]\(\s*)"
    r"(?P<target><[^>\n]+>|[^\s)\n]+)"
    r"(?P<suffix>(?:\s+(?:\"[^\"\n]*\"|'[^'\n]*'|\([^\n)]*\)))?\s*\))"
)
_HTML_MEDIA = re.compile(
    r"(?P<prefix><(?:img|embed)\b[^>]*?\bsrc\s*=\s*[\"'])"
    r"(?P<target>[^\"']+)"
    r"(?P<suffix>[\"'])",
    re.IGNORECASE,
)
_GRAPHICS_PATH = re.compile(r"\\graphicspath\s*\{((?:\{[^{}]*\})+)\}", re.DOTALL)
_INNER_BRACES = re.compile(r"\{([^{}]*)\}")


class AssetManager:
    """Resolve, convert, copy, and validate Markdown media references."""

    def __init__(
        self,
        *,
        source_dir: Path,
        main_file: Path,
        bundle_dir: Path,
        expanded_latex: str,
        render_dpi: int,
        timeout_seconds: int,
        diagnostics: list[Diagnostic],
    ) -> None:
        self.source_dir = source_dir.resolve()
        self.main_file = main_file.resolve()
        self.bundle_dir = bundle_dir.resolve()
        self.render_dpi = render_dpi
        self.timeout_seconds = timeout_seconds
        self.diagnostics = diagnostics
        self.records: list[AssetRecord] = []
        self._recorded_outputs: set[str] = set()
        self._materialized: dict[Path, str] = {}
        self._search_roots = self._build_search_roots(expanded_latex)

    def rewrite_markdown(self, markdown: str) -> str:
        """Materialize every Markdown/HTML media target and rewrite its path."""

        def replace(match: re.Match[str]) -> str:
            original = match.group("target")
            angle_wrapped = original.startswith("<") and original.endswith(">")
            target = original[1:-1] if angle_wrapped else original
            rewritten = self.materialize(html.unescape(target))
            if angle_wrapped:
                rewritten = f"<{rewritten}>"
            return f"{match.group('prefix')}{rewritten}{match.group('suffix')}"

        markdown = _MARKDOWN_IMAGE.sub(replace, markdown)
        return _HTML_MEDIA.sub(replace, markdown)

    def materialize(self, target: str) -> str:
        """Resolve one target into the bundle and return its portable path."""
        cleaned = urllib.parse.unquote(target.strip()).replace("\\", "/")
        parsed = urllib.parse.urlsplit(cleaned)
        if parsed.scheme or parsed.netloc:
            self._error(
                "remote-media", f"Remote media was not bundled: {target}", target
            )
            return target
        reference = parsed.path
        if not reference:
            self._error("empty-media-target", "Media target was empty", target)
            return target
        if _unsafe_relative_path(reference):
            self._error("unsafe-media-path", f"Unsafe media path: {target}", target)
            return target

        existing = self.bundle_dir / reference
        if existing.is_file() and existing.resolve().is_relative_to(self.bundle_dir):
            self._record_existing(
                existing, source=f"generated:{reference}", generated=True
            )
            return Path(reference).as_posix()

        source = self._resolve(reference)
        if source is None:
            self._error("missing-media", f"Could not resolve media: {target}", target)
            return target
        if (materialized := self._materialized.get(source)) is not None:
            return materialized
        materialized = self._copy_or_convert(source)
        self._materialized[source] = materialized
        return materialized

    def validate_markdown(self, markdown: str) -> int:
        """Validate every final media reference and return the unresolved count."""
        unresolved = 0
        for target in media_targets(markdown):
            parsed = urllib.parse.urlsplit(html.unescape(target))
            if parsed.scheme or parsed.netloc or _unsafe_relative_path(parsed.path):
                unresolved += 1
                continue
            path = self.bundle_dir / urllib.parse.unquote(parsed.path)
            try:
                inside_bundle = path.resolve().is_relative_to(self.bundle_dir)
            except OSError:
                inside_bundle = False
            if not inside_bundle or not path.is_file() or path.stat().st_size == 0:
                unresolved += 1
                self._error(
                    "invalid-bundled-media",
                    f"Bundled media is missing, empty, or unsafe: {target}",
                    target,
                )
        return unresolved

    def register_generated(
        self, output: Path, *, source: str, raw_output: Path | None
    ) -> None:
        """Register a preview produced directly inside the bundle."""
        self._record_existing(
            output,
            source=source,
            generated=True,
            raw_output=raw_output,
        )

    def _build_search_roots(self, expanded_latex: str) -> list[Path]:
        roots = [self.main_file.parent, self.source_dir]
        for match in _GRAPHICS_PATH.finditer(expanded_latex):
            for relative in _INNER_BRACES.findall(match.group(1)):
                for base in (self.main_file.parent, self.source_dir):
                    candidate = (base / relative).resolve()
                    if (
                        candidate.is_relative_to(self.source_dir)
                        and candidate not in roots
                    ):
                        roots.append(candidate)
        return roots

    def _resolve(self, reference: str) -> Path | None:
        relative = Path(reference.lstrip("./"))
        candidates: list[Path] = []
        for root in self._search_roots:
            candidates.append(root / relative)
            if not relative.suffix:
                candidates.extend(
                    root / f"{relative}{extension}" for extension in _ASSET_EXTENSIONS
                )
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved.is_relative_to(self.source_dir) and resolved.is_file():
                return resolved

        parent = relative.parent
        name = relative.name.casefold()
        for root in self._search_roots:
            directory = (root / parent).resolve()
            if not directory.is_relative_to(self.source_dir) or not directory.is_dir():
                continue
            for child in directory.iterdir():
                if not child.is_file():
                    continue
                child_name = child.name.casefold()
                if child_name == name or (
                    not relative.suffix
                    and any(child_name == f"{name}{ext}" for ext in _ASSET_EXTENSIONS)
                ):
                    return child.resolve()
        return None

    def _copy_or_convert(self, source: Path) -> str:
        media_type = detect_media_type(source)
        digest = sha256_file(source)
        stem = _safe_stem(source.stem)
        if media_type == "application/pdf":
            return self._convert_vector(source, digest, stem, ".pdf", "pdftocairo")
        if media_type == "application/postscript":
            suffix = ".eps" if source.suffix.lower() == ".eps" else ".ps"
            return self._convert_vector(source, digest, stem, suffix, "ghostscript")

        extension = extension_for_media_type(media_type, source.suffix)
        output = self._unique_output(
            self.bundle_dir / "images" / f"{stem}{extension}", digest
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        if not output.exists():
            shutil.copy2(source, output)
        self._add_record(
            source=source,
            output=output,
            media_type=media_type,
            digest=digest,
            generated=False,
        )
        return output.relative_to(self.bundle_dir).as_posix()

    def _convert_vector(
        self,
        source: Path,
        digest: str,
        stem: str,
        raw_suffix: str,
        converter: str,
    ) -> str:
        raw_output = self._unique_output(
            self.bundle_dir / "raw" / "assets" / f"{stem}{raw_suffix}", digest
        )
        raw_output.parent.mkdir(parents=True, exist_ok=True)
        if not raw_output.exists():
            shutil.copy2(source, raw_output)

        output = self._unique_output(self.bundle_dir / "images" / f"{stem}.png", digest)
        output.parent.mkdir(parents=True, exist_ok=True)
        if not output.exists():
            raw_relative = raw_output.relative_to(self.bundle_dir).as_posix()
            output_relative = output.relative_to(self.bundle_dir)
            try:
                if converter == "pdftocairo":
                    prefix = output_relative.with_suffix("").as_posix()
                    run_sandboxed(
                        [
                            "pdftocairo",
                            "-png",
                            "-singlefile",
                            "-r",
                            str(self.render_dpi),
                            raw_relative,
                            prefix,
                        ],
                        cwd=self.bundle_dir,
                        timeout_seconds=self.timeout_seconds,
                    )
                else:
                    run_sandboxed(
                        [
                            "gs",
                            "-dSAFER",
                            "-dBATCH",
                            "-dNOPAUSE",
                            "-sDEVICE=pngalpha",
                            f"-r{self.render_dpi}",
                            f"-sOutputFile={output_relative.as_posix()}",
                            raw_relative,
                        ],
                        cwd=self.bundle_dir,
                        timeout_seconds=self.timeout_seconds,
                    )
            except CommandError as error:
                self._error(
                    "vector-render-failed",
                    f"Could not render {source.name}: {error}",
                    str(source.relative_to(self.source_dir)),
                )
                self._add_record(
                    source=source,
                    output=raw_output,
                    media_type=detect_media_type(source),
                    digest=digest,
                    generated=False,
                )
                return raw_output.relative_to(self.bundle_dir).as_posix()

        self._add_record(
            source=source,
            output=output,
            media_type="image/png",
            digest=sha256_file(output),
            raw_output=raw_output,
            generated=True,
        )
        return output.relative_to(self.bundle_dir).as_posix()

    def _unique_output(self, desired: Path, digest: str) -> Path:
        if not desired.exists():
            return desired
        if desired.is_file() and sha256_file(desired) == digest:
            return desired
        return desired.with_name(f"{desired.stem}-{digest[:10]}{desired.suffix}")

    def _record_existing(
        self,
        output: Path,
        *,
        source: str,
        generated: bool,
        raw_output: Path | None = None,
    ) -> None:
        if not output.is_file():
            self._error(
                "missing-generated-asset",
                f"Generated asset is missing: {output}",
                source,
            )
            return
        self._add_record(
            source=source,
            output=output,
            media_type=detect_media_type(output),
            digest=sha256_file(output),
            raw_output=raw_output,
            generated=generated,
        )

    def _add_record(
        self,
        *,
        source: Path | str,
        output: Path,
        media_type: str,
        digest: str,
        generated: bool,
        raw_output: Path | None = None,
    ) -> None:
        output_relative = output.relative_to(self.bundle_dir).as_posix()
        if output_relative in self._recorded_outputs:
            return
        if isinstance(source, Path):
            source_value = source.relative_to(self.source_dir).as_posix()
        else:
            source_value = source
        self.records.append(
            AssetRecord(
                source=source_value,
                output=output_relative,
                media_type=media_type,
                sha256=digest,
                raw_output=(
                    raw_output.relative_to(self.bundle_dir).as_posix()
                    if raw_output is not None
                    else None
                ),
                generated=generated,
            )
        )
        self._recorded_outputs.add(output_relative)

    def _error(self, code: str, message: str, source: str | None = None) -> None:
        diagnostic = Diagnostic(
            level=DiagnosticLevel.ERROR,
            code=code,
            message=message,
            source=source,
        )
        if diagnostic not in self.diagnostics:
            self.diagnostics.append(diagnostic)


class PreviewRenderer:
    """Compile isolated source environments and render tight PNG previews."""

    def __init__(
        self,
        *,
        main_file: Path,
        expanded_latex: str,
        bundle_dir: Path,
        manager: AssetManager,
        render_dpi: int,
        timeout_seconds: int,
    ) -> None:
        self.main_file = main_file
        self.bundle_dir = bundle_dir
        self.manager = manager
        self.render_dpi = render_dpi
        self.timeout_seconds = timeout_seconds
        self.preamble = expanded_latex.partition(r"\begin{document}")[0]

    def __call__(self, source: str, kind: str, index: int) -> str | None:
        base = f"latexdl-{kind}-{index:03d}"
        tex_path = self.main_file.parent / f"{base}.tex"
        pdf_path = self.main_file.parent / f"{base}.pdf"
        cropped_path = self.main_file.parent / f"{base}-crop.pdf"
        tex_path.write_text(self._preview_document(source), encoding="utf-8")
        try:
            run_sandboxed(
                [
                    "pdflatex",
                    "-interaction=nonstopmode",
                    "-halt-on-error",
                    "-no-shell-escape",
                    tex_path.name,
                ],
                cwd=self.main_file.parent,
                timeout_seconds=self.timeout_seconds,
            )
            selected_pdf = pdf_path
            try:
                run_sandboxed(
                    ["pdfcrop", pdf_path.name, cropped_path.name],
                    cwd=self.main_file.parent,
                    timeout_seconds=self.timeout_seconds,
                )
                selected_pdf = cropped_path
            except CommandError:
                pass

            raw_output = self.bundle_dir / "raw" / "previews" / f"{base}.pdf"
            image_output = self.bundle_dir / "images" / f"{base}.png"
            raw_output.parent.mkdir(parents=True, exist_ok=True)
            image_output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(selected_pdf, raw_output)
            run_sandboxed(
                [
                    "pdftocairo",
                    "-png",
                    "-singlefile",
                    "-r",
                    str(self.render_dpi),
                    raw_output.relative_to(self.bundle_dir).as_posix(),
                    image_output.with_suffix("")
                    .relative_to(self.bundle_dir)
                    .as_posix(),
                ],
                cwd=self.bundle_dir,
                timeout_seconds=self.timeout_seconds,
            )
            self.manager.register_generated(
                image_output,
                source=f"latex:{kind}:{index}",
                raw_output=raw_output,
            )
            return image_output.relative_to(self.bundle_dir).as_posix()
        except (CommandError, OSError) as error:
            self.manager.diagnostics.append(
                Diagnostic(
                    level=DiagnosticLevel.WARNING,
                    code="preview-render-detail",
                    message=str(error)[-2000:],
                    source=f"{kind}:{index}",
                )
            )
            return None
        finally:
            for suffix in (".aux", ".log", ".out", ".tex", ".pdf"):
                (self.main_file.parent / f"{base}{suffix}").unlink(missing_ok=True)
            cropped_path.unlink(missing_ok=True)

    def _preview_document(self, source: str) -> str:
        preview_package = r"\usepackage[active,tightpage]{preview}"
        body = _preview_body(source)
        return (
            f"{self.preamble}\n{preview_package}\n"
            r"\begin{document}"
            + "\n"
            + r"\begin{preview}"
            + "\n"
            + body
            + "\n"
            + r"\end{preview}"
            + "\n"
            + r"\end{document}"
            + "\n"
        )


def media_targets(markdown: str) -> list[str]:
    """Return Markdown-image and HTML img/embed targets in source order."""
    matches = [
        (match.start(), match.group("target").strip("<>"))
        for pattern in (_MARKDOWN_IMAGE, _HTML_MEDIA)
        for match in pattern.finditer(markdown)
    ]
    return [target for _, target in sorted(matches)]


def detect_media_type(path: Path) -> str:
    """Detect common document media from magic bytes, then its filename."""
    head = path.read_bytes()[:4096]
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if head.startswith(b"%!PS-Adobe"):
        return "application/postscript"
    if b"<svg" in head.lower():
        return "image/svg+xml"
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def extension_for_media_type(media_type: str, fallback: str) -> str:
    mapping = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/svg+xml": ".svg",
    }
    return mapping.get(media_type, fallback.lower() or ".bin")


def _unsafe_relative_path(value: str) -> bool:
    path = Path(value.replace("\\", "/"))
    return path.is_absolute() or ".." in path.parts


def _safe_stem(value: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    if stem:
        return stem
    return f"asset-{hashlib.sha256(value.encode()).hexdigest()[:10]}"


def _preview_body(source: str) -> str:
    body = re.sub(
        r"^\s*\\begin\{(?:figure|table)\*?\}(?:\[[^\]]*\])?",
        "",
        source,
        count=1,
    )
    body = re.sub(
        r"\\end\{(?:figure|table)\*?\}\s*$",
        "",
        body,
        count=1,
    )
    body = _remove_latex_command(body, "caption")
    return _remove_latex_command(body, "label")


def _remove_latex_command(source: str, command: str) -> str:
    pattern = re.compile(rf"\\{re.escape(command)}\*?(?:\s*\[[^\]]*\])?\s*\{{")
    while (match := pattern.search(source)) is not None:
        depth = 1
        cursor = match.end()
        while cursor < len(source) and depth:
            character = source[cursor]
            escaped = cursor > 0 and source[cursor - 1] == "\\"
            if character == "{" and not escaped:
                depth += 1
            elif character == "}" and not escaped:
                depth -= 1
            cursor += 1
        if depth:
            break
        source = source[: match.start()] + source[cursor:]
    return source
