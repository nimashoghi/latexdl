from __future__ import annotations

import hashlib
import importlib.metadata
import json
import logging
import os
import re
import shutil
import tempfile
from collections.abc import Sequence
from pathlib import Path

import platformdirs

from ._assets import AssetManager, PreviewRenderer
from ._bibtex import detect_and_collect_bibtex
from ._commands import collect_tool_versions
from ._metadata import fetch_arxiv_metadata
from ._pandoc import (
    ast_to_gfm,
    count_ast_nodes,
    latex_to_ast,
    preserve_semantic_inlines,
    recover_figures,
    recover_tables,
    source_environments,
)
from ._source import SourceBundle, acquire_source, parse_arxiv_id, sha256_file
from .expand import ExpandError, expand_latex_file
from .models import (
    ConversionReport,
    ConversionRequest,
    ConversionResult,
    ConversionStatus,
    Diagnostic,
    DiagnosticLevel,
)

log = logging.getLogger(__name__)


def convert_arxiv(request: ConversionRequest) -> ConversionResult:
    """Convert one arXiv source package into an atomic, portable bundle."""
    destination = request.output_dir.expanduser().resolve()
    if destination.exists() and not request.force:
        raise FileExistsError(f"output directory already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)

    cache_dir = (
        request.cache_dir.expanduser().resolve()
        if request.cache_dir is not None
        else platformdirs.user_cache_path("latexdl")
    )
    cache_dir.mkdir(parents=True, exist_ok=True)

    base_id, requested_version = parse_arxiv_id(request.paper)
    metadata = fetch_arxiv_metadata(f"{base_id}{requested_version or ''}")
    source = acquire_source(
        request.paper,
        cache_dir,
        metadata,
        timeout_seconds=request.timeout_seconds,
    )
    tools = collect_tool_versions()
    version = _package_version()
    options = _report_options(request)
    cache_key = _cache_key(source, options, tools, version)
    cached_bundle = cache_dir / "results" / cache_key / "bundle"

    if request.use_cache and _valid_cached_bundle(cached_bundle):
        _copy_tree_atomically(cached_bundle, destination, force=request.force)
        report = ConversionReport.model_validate_json(
            (destination / "conversion.json").read_text()
        )
        return ConversionResult(
            bundle_dir=destination,
            paper_path=destination / "paper.md",
            report_path=destination / "conversion.json",
            metadata=metadata,
            report=report,
        )

    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.latexdl-", dir=destination.parent)
    )
    try:
        report = _build_bundle(
            request=request,
            source=source,
            staging=staging,
            cache_dir=cache_dir,
            cache_key=cache_key,
            options=options,
            tools=tools,
            version=version,
        )
        _install_tree(staging, destination, force=request.force)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    if request.use_cache:
        try:
            cached_bundle.parent.mkdir(parents=True, exist_ok=True)
            _copy_tree_atomically(destination, cached_bundle, force=True)
        except OSError as error:
            log.warning("could not populate result cache %s: %s", cached_bundle, error)

    return ConversionResult(
        bundle_dir=destination,
        paper_path=destination / "paper.md",
        report_path=destination / "conversion.json",
        metadata=source.metadata,
        report=report,
    )


def convert_many(requests: Sequence[ConversionRequest]) -> list[ConversionResult]:
    """Convert several papers in request order."""
    return [convert_arxiv(request) for request in requests]


def _build_bundle(
    *,
    request: ConversionRequest,
    source: SourceBundle,
    staging: Path,
    cache_dir: Path,
    cache_key: str,
    options: dict[str, str | int | bool],
    tools: dict[str, str],
    version: str,
) -> ConversionReport:
    diagnostics: list[Diagnostic] = []
    if source.metadata is None:
        diagnostics.append(
            Diagnostic(
                level=DiagnosticLevel.WARNING,
                code="metadata-unavailable",
                message="arXiv metadata was unavailable; source conversion continued",
            )
        )

    (staging / "images").mkdir(parents=True)
    (staging / "raw").mkdir(parents=True)
    build_parent = cache_dir / "build"
    build_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="latexdl-", dir=build_parent) as build_name:
        build_root = Path(build_name)
        build_source = build_root / "source"
        shutil.copytree(source.source_dir, build_source, ignore=_source_copy_ignore)
        main_file = _find_main_latex_file(build_source)
        if main_file is None:
            raise RuntimeError(
                f"could not find the main LaTeX file for {source.arxiv_id}"
            )

        raw_main = staging / "raw" / "main.tex"
        shutil.copy2(main_file, raw_main)
        raw_expanded = staging / "raw" / "expanded.tex"
        try:
            expanded = expand_latex_file(
                main_file,
                raw_expanded,
                keep_comments=request.keep_comments,
                timeout_seconds=request.timeout_seconds,
            )
        except ExpandError as error:
            expanded = main_file.read_text(encoding="utf-8", errors="replace")
            raw_expanded.write_text(expanded, encoding="utf-8")
            diagnostics.append(
                Diagnostic(
                    level=DiagnosticLevel.ERROR,
                    code="latex-expansion-failed",
                    message=str(error),
                    source=main_file.relative_to(build_source).as_posix(),
                )
            )

        source_figures = source_environments(expanded, "figure")
        source_tables = source_environments(expanded, "table")
        manager = AssetManager(
            source_dir=build_source,
            main_file=main_file,
            bundle_dir=staging,
            expanded_latex=expanded,
            render_dpi=request.render_dpi,
            timeout_seconds=request.timeout_seconds,
            diagnostics=diagnostics,
        )
        renderer = PreviewRenderer(
            main_file=main_file,
            expanded_latex=expanded,
            bundle_dir=staging,
            manager=manager,
            render_dpi=request.render_dpi,
            timeout_seconds=request.timeout_seconds,
        )

        figures_recovered = 0
        tables_recovered = 0
        ast_figures = 0
        ast_tables = 0
        citations_expected = 0
        citations_preserved = 0
        math_expected = 0
        math_preserved = 0
        try:
            ast = latex_to_ast(
                expanded,
                cwd=main_file.parent,
                preserve_macros=request.preserve_macros,
                timeout_seconds=request.timeout_seconds,
            )
            ast_figures = count_ast_nodes(ast, "Figure")
            ast_tables = count_ast_nodes(ast, "Table")
            citations_expected = count_ast_nodes(ast, "Cite")
            math_expected = count_ast_nodes(ast, "Math")
            figures_recovered = recover_figures(
                ast, source_figures, renderer, diagnostics
            )
            tables_recovered = recover_tables(ast, source_tables, renderer, diagnostics)
            citations_preserved, math_preserved = preserve_semantic_inlines(ast)
            markdown = ast_to_gfm(
                ast,
                cwd=main_file.parent,
                timeout_seconds=request.timeout_seconds,
            )
        except (RuntimeError, ValueError, json.JSONDecodeError) as error:
            diagnostics.append(
                Diagnostic(
                    level=DiagnosticLevel.ERROR,
                    code="pandoc-conversion-failed",
                    message=str(error),
                )
            )
            markdown = f"```latex\n{expanded.rstrip()}\n```\n"

        markdown = manager.rewrite_markdown(markdown)
        if request.include_metadata and source.metadata is not None:
            markdown = source.metadata.format_for_markdown() + markdown.lstrip()
        if request.include_bibliography:
            try:
                bibliography = detect_and_collect_bibtex(
                    build_source,
                    expanded,
                    main_tex_path=main_file,
                    markdown=True,
                    parse_citations=False,
                )
            except Exception as error:
                diagnostics.append(
                    Diagnostic(
                        level=DiagnosticLevel.ERROR,
                        code="bibliography-conversion-failed",
                        message=str(error),
                    )
                )
            else:
                if bibliography is not None and bibliography.references_str.strip():
                    markdown = (
                        f"{markdown.rstrip()}\n\n# References\n\n"
                        f"{bibliography.references_str.strip()}\n"
                    )

        markdown = _normalize_markdown(markdown)
        (staging / "paper.md").write_text(markdown, encoding="utf-8")
        unresolved_media = manager.validate_markdown(markdown)

    figures_expected = max(len(source_figures), ast_figures)
    tables_expected = max(len(source_tables), ast_tables)
    figures_recovered = min(
        figures_expected,
        max(0, figures_recovered - unresolved_media),
    )
    tables_recovered = min(tables_expected, tables_recovered)
    if figures_recovered < figures_expected:
        diagnostics.append(
            Diagnostic(
                level=DiagnosticLevel.ERROR,
                code="incomplete-figures",
                message=f"Recovered {figures_recovered} of {figures_expected} figures",
            )
        )
    if tables_recovered < tables_expected:
        diagnostics.append(
            Diagnostic(
                level=DiagnosticLevel.ERROR,
                code="incomplete-tables",
                message=f"Recovered {tables_recovered} of {tables_expected} tables",
            )
        )
    if citations_preserved < citations_expected:
        diagnostics.append(
            Diagnostic(
                level=DiagnosticLevel.ERROR,
                code="incomplete-citations",
                message=(
                    f"Preserved {citations_preserved} of {citations_expected} citations"
                ),
            )
        )
    if math_preserved < math_expected:
        diagnostics.append(
            Diagnostic(
                level=DiagnosticLevel.ERROR,
                code="incomplete-math",
                message=f"Preserved {math_preserved} of {math_expected} math expressions",
            )
        )

    status = (
        ConversionStatus.PARTIAL
        if any(item.level is DiagnosticLevel.ERROR for item in diagnostics)
        else ConversionStatus.COMPLETE
    )
    report = ConversionReport(
        latexdl_version=version,
        status=status,
        arxiv_id=source.arxiv_id,
        source_version=source.source_version,
        source_sha256=source.archive_sha256,
        cache_key=cache_key,
        figures_expected=figures_expected,
        figures_recovered=figures_recovered,
        tables_expected=tables_expected,
        tables_recovered=tables_recovered,
        citations_expected=citations_expected,
        citations_preserved=citations_preserved,
        math_expected=math_expected,
        math_preserved=math_preserved,
        options=options,
        assets=manager.records,
        diagnostics=diagnostics,
        tools=tools,
    )
    (staging / "conversion.json").write_text(
        report.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    (staging / "conversion-report.md").write_text(
        _render_report_markdown(report),
        encoding="utf-8",
    )
    return report


def _normalize_markdown(markdown: str) -> str:
    return "\n".join(line.rstrip() for line in markdown.splitlines()) + "\n"


def _find_main_latex_file(directory: Path) -> Path | None:
    candidates: list[tuple[float, Path]] = []
    for path in directory.rglob("*"):
        if not path.is_file() or path.suffix.lower() != ".tex":
            continue
        if path.name.startswith(("expanded_", ".latexdl-")):
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")
        score = min(path.stat().st_size / 1000, 5)
        if path.name.lower() in {"main.tex", "paper.tex", "article.tex"}:
            score += 5
        if r"\documentclass" in content:
            score += 4
        if r"\begin{document}" in content and r"\end{document}" in content:
            score += 5
        score += min(len(re.findall(r"\\(?:input|include)\b", content)), 3)
        if r"\bibliography" in content or r"\begin{thebibliography}" in content:
            score += 2
        candidates.append((score, path))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def _report_options(request: ConversionRequest) -> dict[str, str | int | bool]:
    return {
        "include_metadata": request.include_metadata,
        "include_bibliography": request.include_bibliography,
        "keep_comments": request.keep_comments,
        "preserve_macros": request.preserve_macros,
        "timeout_seconds": request.timeout_seconds,
        "render_dpi": request.render_dpi,
    }


def _cache_key(
    source: SourceBundle,
    options: dict[str, str | int | bool],
    tools: dict[str, str],
    version: str,
) -> str:
    identity = {
        "schema": 1,
        "latexdl": version,
        "arxiv_id": source.arxiv_id,
        "source_version": source.source_version,
        "source_sha256": source.archive_sha256,
        "options": options,
        "tools": tools,
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _package_version() -> str:
    try:
        return importlib.metadata.version("latexdl")
    except importlib.metadata.PackageNotFoundError:
        return "3.0.1"


def _source_copy_ignore(_directory: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if name == ".latexdl-source-sha256"
        or (name.startswith("expanded_") and name.endswith(".tex"))
    }


def _valid_cached_bundle(path: Path) -> bool:
    required = (
        path / "paper.md",
        path / "conversion.json",
        path / "conversion-report.md",
        path / "raw" / "main.tex",
        path / "raw" / "expanded.tex",
    )
    if any(not item.is_file() or item.stat().st_size == 0 for item in required):
        return False
    try:
        report = ConversionReport.model_validate_json(
            (path / "conversion.json").read_text()
        )
    except (OSError, ValueError):
        return False
    for asset in report.assets:
        output = path / asset.output
        if (
            not output.resolve().is_relative_to(path.resolve())
            or not output.is_file()
            or output.stat().st_size == 0
            or sha256_file(output) != asset.sha256
        ):
            return False
        if asset.raw_output is not None:
            raw_output = path / asset.raw_output
            if (
                not raw_output.resolve().is_relative_to(path.resolve())
                or not raw_output.is_file()
                or raw_output.stat().st_size == 0
            ):
                return False
    return True


def _copy_tree_atomically(source: Path, destination: Path, *, force: bool) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.copy-", dir=destination.parent)
    )
    shutil.rmtree(staging)
    try:
        shutil.copytree(source, staging)
        _install_tree(staging, destination, force=force)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _install_tree(staging: Path, destination: Path, *, force: bool) -> None:
    if not destination.exists():
        os.replace(staging, destination)
        return
    if not force:
        raise FileExistsError(f"output directory already exists: {destination}")

    backup = destination.with_name(
        f".{destination.name}.backup-{hashlib.sha256(os.urandom(32)).hexdigest()[:10]}"
    )
    os.replace(destination, backup)
    try:
        os.replace(staging, destination)
    except BaseException:
        os.replace(backup, destination)
        raise
    shutil.rmtree(backup, ignore_errors=True)


def _render_report_markdown(report: ConversionReport) -> str:
    lines = [
        "# Conversion report",
        "",
        f"- Status: `{report.status.value}`",
        f"- arXiv source: `{report.source_version}`",
        f"- Source SHA-256: `{report.source_sha256}`",
        f"- Figures: {report.figures_recovered}/{report.figures_expected}",
        f"- Tables: {report.tables_recovered}/{report.tables_expected}",
        f"- Citations: {report.citations_preserved}/{report.citations_expected}",
        f"- Math: {report.math_preserved}/{report.math_expected}",
        f"- Assets: {len(report.assets)}",
        "",
        "## Diagnostics",
        "",
    ]
    if report.diagnostics:
        lines.extend(
            f"- `{item.level.value}` `{item.code}`: {item.message}"
            for item in report.diagnostics
        )
    else:
        lines.append("No diagnostics.")
    lines.extend(["", "## Assets", ""])
    if report.assets:
        lines.extend(
            f"- `{item.output}` from `{item.source}` ({item.media_type}, `{item.sha256}`)"
            for item in report.assets
        )
    else:
        lines.append("No assets.")
    return "\n".join(lines) + "\n"
