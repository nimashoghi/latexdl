from __future__ import annotations

from pathlib import Path

from latexdl._pandoc import (
    ast_to_gfm,
    preserve_semantic_inlines,
    recover_figures,
    recover_tables,
    source_environments,
)
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


def test_citations_and_math_are_preserved_as_raw_markdown(tmp_path: Path) -> None:
    ast = {
        "pandoc-api-version": [1, 23, 1],
        "meta": {},
        "blocks": [
            {
                "t": "Para",
                "c": [
                    {
                        "t": "Cite",
                        "c": [
                            [
                                {
                                    "citationId": "smith2020",
                                    "citationPrefix": [],
                                    "citationSuffix": [
                                        {"t": "Str", "c": "p."},
                                        {"t": "Space"},
                                        {"t": "Str", "c": "4"},
                                    ],
                                    "citationMode": {"t": "NormalCitation"},
                                },
                                {
                                    "citationId": "jones2021",
                                    "citationPrefix": [],
                                    "citationSuffix": [],
                                    "citationMode": {"t": "SuppressAuthor"},
                                },
                            ],
                            [],
                        ],
                    },
                    {"t": "Space"},
                    {"t": "Math", "c": [{"t": "InlineMath"}, "x+y"]},
                    {"t": "Space"},
                    {"t": "Math", "c": [{"t": "DisplayMath"}, "a=b"]},
                ],
            }
        ],
    }

    assert preserve_semantic_inlines(ast) == (1, 2)
    markdown = ast_to_gfm(ast, cwd=tmp_path, timeout_seconds=30)

    assert "[@smith2020, p. 4; -@jones2021]" in markdown
    assert "$x+y$" in markdown
    assert "$$\na=b\n$$" in markdown
    assert "$`" not in markdown
    assert "``` math" not in markdown
