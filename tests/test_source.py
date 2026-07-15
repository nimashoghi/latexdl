from __future__ import annotations

import gzip
import io
import tarfile
from pathlib import Path

import pytest

from latexdl._source import _extract_archive_atomically, parse_arxiv_id


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2505.11831", ("2505.11831", None)),
        ("2505.11831v2", ("2505.11831", "v2")),
        ("https://arxiv.org/abs/2505.11831v2", ("2505.11831", "v2")),
        ("https://export.arxiv.org/pdf/2505.11831.pdf", ("2505.11831", None)),
        ("hep-th/9901001v3", ("hep-th/9901001", "v3")),
    ],
)
def test_parse_arxiv_id(value: str, expected: tuple[str, str | None]) -> None:
    assert parse_arxiv_id(value) == expected


def test_safe_tar_extraction(tmp_path: Path) -> None:
    archive = tmp_path / "source.tar.gz"
    payload = b"\\documentclass{article}"
    with tarfile.open(archive, "w:gz") as handle:
        info = tarfile.TarInfo("paper/main.tex")
        info.size = len(payload)
        handle.addfile(info, io.BytesIO(payload))

    destination = tmp_path / "source"
    _extract_archive_atomically(archive, destination, "abc")

    assert (destination / "paper" / "main.tex").read_bytes() == payload
    assert (destination / ".latexdl-source-sha256").read_text() == "abc"


@pytest.mark.parametrize("member_name", ["../escape.tex", "/absolute.tex"])
def test_tar_path_traversal_is_rejected(tmp_path: Path, member_name: str) -> None:
    archive = tmp_path / "source.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        info = tarfile.TarInfo(member_name)
        info.size = 1
        handle.addfile(info, io.BytesIO(b"x"))

    with pytest.raises(ValueError, match="unsafe archive path"):
        _extract_archive_atomically(archive, tmp_path / "source", "abc")
    assert not (tmp_path / "source").exists()


def test_tar_links_are_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "source.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        info = tarfile.TarInfo("link")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        handle.addfile(info)

    with pytest.raises(ValueError, match="unsafe tar member type"):
        _extract_archive_atomically(archive, tmp_path / "source", "abc")


def test_single_gzip_source_is_supported(tmp_path: Path) -> None:
    archive = tmp_path / "source.gz"
    with gzip.open(archive, "wb") as handle:
        handle.write(b"\\documentclass{article}")

    destination = tmp_path / "source"
    _extract_archive_atomically(archive, destination, "abc")

    assert (destination / "main.tex").read_text() == r"\documentclass{article}"
