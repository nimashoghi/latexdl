from __future__ import annotations

from pathlib import Path

from latexdl import ConversionRequest, ConversionStatus, convert_arxiv
from latexdl._source import SourceBundle


def test_convert_arxiv_builds_complete_atomic_bundle(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "figure.png").write_bytes(b"\x89PNG\r\n\x1a\nfigure")
    latex = r"""
\documentclass{article}
\usepackage{graphicx}
\begin{document}
\section{Result}
\begin{figure}
\includegraphics{figure}
\caption{A figure}
\end{figure}
\begin{table}
\caption{A table}
\begin{tabular}{cc}A & B \\\\ 1 & 2\end{tabular}
\end{table}
\end{document}
"""
    (source / "main.tex").write_text(latex)
    archive = tmp_path / "source.archive"
    archive.write_bytes(b"archive")
    source_bundle = SourceBundle(
        arxiv_id="2505.11831",
        source_version="2505.11831v2",
        source_dir=source,
        archive_path=archive,
        archive_sha256="a" * 64,
        metadata=None,
    )

    monkeypatch.setattr("latexdl.converter.fetch_arxiv_metadata", lambda _paper: None)
    monkeypatch.setattr(
        "latexdl.converter.acquire_source",
        lambda *_args, **_kwargs: source_bundle,
    )
    monkeypatch.setattr(
        "latexdl.converter.collect_tool_versions",
        lambda: {"pandoc": "test"},
    )

    def fake_expand(
        main_file: Path,
        output_path: Path,
        *,
        keep_comments: bool,
        timeout_seconds: int,
    ) -> str:
        del keep_comments, timeout_seconds
        content = main_file.read_text()
        output_path.write_text(content)
        return content

    monkeypatch.setattr("latexdl.converter.expand_latex_file", fake_expand)

    destination = tmp_path / "bundle"
    result = convert_arxiv(
        ConversionRequest(
            paper="2505.11831v2",
            output_dir=destination,
            cache_dir=tmp_path / "cache",
            use_cache=False,
            include_metadata=False,
            include_bibliography=False,
        )
    )

    assert result.report.status is ConversionStatus.COMPLETE
    assert result.report.figures_recovered == result.report.figures_expected == 1
    assert result.report.tables_recovered == result.report.tables_expected == 1
    assert (destination / "paper.md").is_file()
    assert (destination / "images" / "figure.png").is_file()
    assert (destination / "raw" / "main.tex").is_file()
    assert (destination / "raw" / "expanded.tex").is_file()
    assert (destination / "conversion.json").is_file()
    assert (destination / "conversion-report.md").is_file()


def test_existing_destination_is_not_touched_without_force(tmp_path: Path) -> None:
    destination = tmp_path / "bundle"
    destination.mkdir()
    marker = destination / "user-file"
    marker.write_text("keep")

    try:
        convert_arxiv(
            ConversionRequest(
                paper="2505.11831",
                output_dir=destination,
                cache_dir=tmp_path / "cache",
            )
        )
    except FileExistsError:
        pass
    else:
        raise AssertionError("expected FileExistsError")

    assert marker.read_text() == "keep"
