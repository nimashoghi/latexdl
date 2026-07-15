from __future__ import annotations

import contextlib
import fcntl
import gzip
import hashlib
import os
import re
import shutil
import tarfile
import tempfile
import urllib.parse
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import requests

from ._types import ArxivMetadata

_ARXIV_ID_PATTERN = re.compile(
    r"^(?P<base>(?:[a-z-]+(?:\.[A-Z]{2})?/\d{7}|\d{4}\.\d{4,5}))(?P<version>v\d+)?$",
    re.IGNORECASE,
)
_MAX_ARCHIVE_BYTES = 2 * 1024**3
_MAX_EXTRACTED_BYTES = 8 * 1024**3
_MAX_MEMBERS = 100_000


@dataclass(frozen=True, kw_only=True)
class SourceBundle:
    arxiv_id: str
    source_version: str
    source_dir: Path
    archive_path: Path
    archive_sha256: str
    metadata: ArxivMetadata | None


def parse_arxiv_id(value: str) -> tuple[str, str | None]:
    """Parse an arXiv ID or canonical arXiv abs/PDF/source URL."""
    candidate = value.strip()
    if candidate.startswith(("http://", "https://")):
        parsed = urllib.parse.urlparse(candidate)
        if parsed.hostname not in {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}:
            raise ValueError(f"Not an arXiv URL: {value}")
        parts = [part for part in parsed.path.split("/") if part]
        if not parts or parts[0] not in {"abs", "pdf", "src"}:
            raise ValueError(f"Unsupported arXiv URL: {value}")
        candidate = "/".join(parts[1:])
        if candidate.endswith(".pdf"):
            candidate = candidate[:-4]

    match = _ARXIV_ID_PATTERN.fullmatch(candidate)
    if match is None:
        raise ValueError(f"Invalid arXiv ID: {value}")
    return match.group("base"), match.group("version")


def acquire_source(
    paper: str,
    cache_dir: Path,
    metadata: ArxivMetadata | None,
    *,
    timeout_seconds: int,
) -> SourceBundle:
    """Download and safely extract a versioned arXiv source archive."""
    base_id, requested_version = parse_arxiv_id(paper)
    source_version = _resolve_source_version(base_id, requested_version, metadata)
    safe_id = base_id.replace("/", "_")
    version_dir = cache_dir / "sources" / safe_id / source_version.replace("/", "_")
    archive_path = version_dir / "source.archive"
    source_dir = version_dir / "source"
    version_dir.mkdir(parents=True, exist_ok=True)

    with _exclusive_lock(version_dir / ".lock"):
        if not archive_path.is_file():
            legacy = _find_legacy_archive(cache_dir, base_id, source_version)
            if legacy is not None:
                _atomic_copy(legacy, archive_path)
            else:
                _download_archive(
                    f"{base_id}{requested_version or ''}",
                    archive_path,
                    timeout_seconds=timeout_seconds,
                )

        archive_sha256 = sha256_file(archive_path)
        marker = source_dir / ".latexdl-source-sha256"
        if (
            not source_dir.is_dir()
            or not marker.is_file()
            or marker.read_text() != archive_sha256
        ):
            _extract_archive_atomically(archive_path, source_dir, archive_sha256)

    return SourceBundle(
        arxiv_id=base_id,
        source_version=source_version,
        source_dir=source_dir,
        archive_path=archive_path,
        archive_sha256=archive_sha256,
        metadata=metadata,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_source_version(
    base_id: str,
    requested_version: str | None,
    metadata: ArxivMetadata | None,
) -> str:
    if requested_version is not None:
        return f"{base_id}{requested_version}"
    if metadata is not None:
        metadata_id = metadata.entry_id.rstrip("/").rsplit("/", 1)[-1]
        if _ARXIV_ID_PATTERN.fullmatch(metadata_id):
            return metadata_id
    return base_id


def _find_legacy_archive(
    cache_dir: Path, base_id: str, source_version: str
) -> Path | None:
    legacy_root = cache_dir / base_id / source_version
    candidates = [
        legacy_root / f"{base_id}.tar.gz",
        legacy_root / f"{base_id.replace('/', '_')}.tar.gz",
    ]
    return next((path for path in candidates if path.is_file()), None)


def _download_archive(
    arxiv_id: str, destination: Path, *, timeout_seconds: int
) -> None:
    url = f"https://arxiv.org/src/{urllib.parse.quote(arxiv_id, safe='/')}"
    headers = {"User-Agent": "latexdl/3 (+https://github.com/nimashoghi/latexdl)"}
    with requests.get(
        url,
        headers=headers,
        stream=True,
        timeout=(15, timeout_seconds),
    ) as response:
        response.raise_for_status()
        if (length := response.headers.get("Content-Length")) is not None:
            if int(length) > _MAX_ARCHIVE_BYTES:
                raise ValueError(
                    f"arXiv source archive exceeds {_MAX_ARCHIVE_BYTES} bytes"
                )

        with tempfile.NamedTemporaryFile(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".part",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            total = 0
            try:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > _MAX_ARCHIVE_BYTES:
                        raise ValueError(
                            f"arXiv source archive exceeds {_MAX_ARCHIVE_BYTES} bytes"
                        )
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise
    os.replace(temporary, destination)


def _extract_archive_atomically(
    archive_path: Path,
    destination: Path,
    archive_sha256: str,
) -> None:
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
    )
    try:
        if tarfile.is_tarfile(archive_path):
            _extract_tar(archive_path, temporary)
        else:
            _extract_single_gzip(archive_path, temporary)
        if not any(path.is_file() for path in temporary.rglob("*")):
            raise ValueError("arXiv source archive was empty")
        (temporary / ".latexdl-source-sha256").write_text(archive_sha256)
        if destination.exists():
            shutil.rmtree(destination)
        os.replace(temporary, destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _extract_tar(archive_path: Path, destination: Path) -> None:
    total = 0
    with tarfile.open(archive_path, mode="r:*") as archive:
        members = archive.getmembers()
        if len(members) > _MAX_MEMBERS:
            raise ValueError(f"source archive has more than {_MAX_MEMBERS} members")
        for member in members:
            relative = _safe_member_path(member.name)
            if member.isdir():
                (destination / relative).mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise ValueError(f"unsafe tar member type: {member.name}")
            total += member.size
            if total > _MAX_EXTRACTED_BYTES:
                raise ValueError(
                    f"source archive expands beyond {_MAX_EXTRACTED_BYTES} bytes"
                )
            source = archive.extractfile(member)
            if source is None:
                raise ValueError(f"could not read tar member: {member.name}")
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def _extract_single_gzip(archive_path: Path, destination: Path) -> None:
    target = destination / "main.tex"
    with gzip.open(archive_path, "rb") as source, target.open("wb") as output:
        total = 0
        while chunk := source.read(1024 * 1024):
            total += len(chunk)
            if total > _MAX_EXTRACTED_BYTES:
                raise ValueError(
                    f"source archive expands beyond {_MAX_EXTRACTED_BYTES} bytes"
                )
            output.write(chunk)


def _safe_member_path(name: str) -> Path:
    normalized = PurePosixPath(name.replace("\\", "/"))
    if normalized.is_absolute() or ".." in normalized.parts:
        raise ValueError(f"unsafe archive path: {name}")
    parts = [part for part in normalized.parts if part not in {"", "."}]
    if not parts:
        raise ValueError(f"empty archive path: {name}")
    return Path(*parts)


def _atomic_copy(source: Path, destination: Path) -> None:
    with tempfile.NamedTemporaryFile(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".part",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        try:
            with source.open("rb") as input_handle:
                shutil.copyfileobj(input_handle, handle)
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    os.replace(temporary, destination)


@contextlib.contextmanager
def _exclusive_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
