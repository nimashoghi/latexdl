from __future__ import annotations

from latexdl._pandoc import recover_figures, recover_tables, source_environments
from latexdl.models import Diagnostic


def _empty_figure() -> dict:
    return {
        "t": "Figure",
        "c": [
            ["fig:test", [], []],
            [None, [{"t": "Plain", "c": [{"t": "Str", "c": "Caption"}]}]],
            [],
        ],
    }


def test_source_environments_handles_starred_variants() -> None:
    source = r"""
\begin{figure}one\end{figure}
\begin{figure*}two\end{figure*}
\begin{table}three\end{table}
"""
    assert len(source_environments(source, "figure")) == 2
    assert len(source_environments(source, "table")) == 1


def test_empty_figure_is_recovered_in_place() -> None:
    ast = {"blocks": [_empty_figure()]}
    diagnostics: list[Diagnostic] = []

    recovered = recover_figures(
        ast,
        [r"\begin{figure}source\end{figure}"],
        lambda _source, _kind, _index: "images/recovered.png",
        diagnostics,
    )

    assert recovered == 1
    assert ast["blocks"][0]["c"][2][0]["t"] == "Para"
    assert ast["blocks"][0]["c"][2][0]["c"][0]["t"] == "Image"
    assert diagnostics == []


def test_dropped_table_gets_visual_and_raw_fallback() -> None:
    ast = {"blocks": []}
    diagnostics: list[Diagnostic] = []
    source = r"\begin{table}\begin{tabular}{c}x\end{tabular}\end{table}"

    recovered = recover_tables(
        ast,
        [source],
        lambda _source, _kind, _index: "images/table.png",
        diagnostics,
    )

    assert recovered == 1
    assert [block["t"] for block in ast["blocks"]] == ["Header", "Para", "CodeBlock"]
    assert ast["blocks"][-1]["c"][1] == source
    assert diagnostics == []
