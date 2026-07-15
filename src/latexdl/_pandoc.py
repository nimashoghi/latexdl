from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from ._commands import pandoc_path, run_command
from .models import Diagnostic, DiagnosticLevel

PandocNode = dict[str, Any]
RenderPreview = Callable[[str, str, int], str | None]

_FIGURE_ENVIRONMENT = re.compile(
    r"\\begin\{figure(?P<star>\*)?\}(?P<body>.*?)"
    r"\\end\{figure(?P=star)?\}",
    re.DOTALL,
)
_TABLE_ENVIRONMENT = re.compile(
    r"\\begin\{table(?P<star>\*)?\}(?P<body>.*?)"
    r"\\end\{table(?P=star)?\}",
    re.DOTALL,
)


def latex_to_ast(
    content: str,
    *,
    cwd: Path,
    preserve_macros: bool,
    timeout_seconds: int,
) -> PandocNode:
    """Parse LaTeX into Pandoc's JSON AST with a killable process."""
    from_format = "latex-latex_macros" if preserve_macros else "latex"
    result = run_command(
        [pandoc_path(), f"--from={from_format}", "--to=json"],
        cwd=cwd,
        timeout_seconds=timeout_seconds,
        input_text=content,
    )
    parsed = json.loads(result.stdout)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("blocks"), list):
        raise ValueError("Pandoc returned an invalid JSON document")
    return parsed


def ast_to_gfm(ast: PandocNode, *, cwd: Path, timeout_seconds: int) -> str:
    """Write a Pandoc JSON AST as portable GitHub-Flavored Markdown."""
    result = run_command(
        [
            pandoc_path(),
            "--from=json",
            "--to=gfm+raw_html",
            "--wrap=none",
        ],
        cwd=cwd,
        timeout_seconds=timeout_seconds,
        input_text=json.dumps(ast, ensure_ascii=False),
    )
    return result.stdout


def source_environments(content: str, environment: str) -> list[str]:
    """Extract complete top-level figure or table environments in source order."""
    if environment == "figure":
        pattern = _FIGURE_ENVIRONMENT
    elif environment == "table":
        pattern = _TABLE_ENVIRONMENT
    else:
        raise ValueError(f"unsupported environment: {environment}")
    environments: list[str] = []
    for match in pattern.finditer(content):
        star = match.group("star") or ""
        environments.append(
            f"\\begin{{{environment}{star}}}{match.group('body')}"
            f"\\end{{{environment}{star}}}"
        )
    return environments


def recover_figures(
    ast: PandocNode,
    source_figures: list[str],
    render_preview: RenderPreview,
    diagnostics: list[Diagnostic],
) -> int:
    """Render empty or dropped figure environments back into the AST."""
    figures = list(_nodes_of_type(ast.get("blocks", []), "Figure"))
    recovered = 0
    for index, figure in enumerate(figures):
        if _contains_node(figure, "Image"):
            recovered += 1
            continue
        if index >= len(source_figures):
            diagnostics.append(
                Diagnostic(
                    level=DiagnosticLevel.ERROR,
                    code="figure-without-source",
                    message=f"Pandoc figure {index + 1} had no image or source environment",
                )
            )
            continue
        output = render_preview(source_figures[index], "figure", index + 1)
        if output is None:
            diagnostics.append(
                Diagnostic(
                    level=DiagnosticLevel.ERROR,
                    code="figure-preview-failed",
                    message=f"Could not render figure {index + 1}",
                )
            )
            _append_raw_latex(figure, source_figures[index])
            continue
        _set_figure_image(figure, output, f"Recovered figure {index + 1}")
        recovered += 1

    if len(source_figures) <= len(figures):
        return recovered

    blocks = ast["blocks"]
    blocks.append(_header(2, "Recovered figures"))
    for index in range(len(figures), len(source_figures)):
        source = source_figures[index]
        output = render_preview(source, "figure", index + 1)
        if output is None:
            diagnostics.append(
                Diagnostic(
                    level=DiagnosticLevel.ERROR,
                    code="dropped-figure-preview-failed",
                    message=f"Pandoc dropped figure {index + 1}, and its preview failed",
                )
            )
            blocks.append(_code_block(source, "latex"))
            continue
        blocks.append(_image_paragraph(output, f"Recovered figure {index + 1}"))
        blocks.append(_code_block(source, "latex"))
        recovered += 1
    return recovered


def recover_tables(
    ast: PandocNode,
    source_tables: list[str],
    render_preview: RenderPreview,
    diagnostics: list[Diagnostic],
) -> int:
    """Append visual and raw-LaTeX fallbacks for tables Pandoc dropped."""
    tables = list(_nodes_of_type(ast.get("blocks", []), "Table"))
    recovered = len(tables)
    if len(source_tables) <= len(tables):
        return recovered

    blocks = ast["blocks"]
    blocks.append(_header(2, "Recovered tables"))
    for index in range(len(tables), len(source_tables)):
        source = source_tables[index]
        output = render_preview(source, "table", index + 1)
        if output is None:
            diagnostics.append(
                Diagnostic(
                    level=DiagnosticLevel.ERROR,
                    code="table-preview-failed",
                    message=f"Pandoc dropped table {index + 1}, and its preview failed",
                )
            )
        else:
            blocks.append(_image_paragraph(output, f"Recovered table {index + 1}"))
            recovered += 1
        blocks.append(_code_block(source, "latex"))
    return recovered


def count_ast_nodes(ast: PandocNode, node_type: str) -> int:
    """Count Pandoc nodes of one type recursively."""
    return sum(1 for _ in _nodes_of_type(ast.get("blocks", []), node_type))


def _nodes_of_type(value: Any, node_type: str) -> Iterator[PandocNode]:
    if isinstance(value, dict):
        if value.get("t") == node_type:
            yield value
        for child in value.values():
            yield from _nodes_of_type(child, node_type)
    elif isinstance(value, list):
        for child in value:
            yield from _nodes_of_type(child, node_type)


def _contains_node(value: Any, node_type: str) -> bool:
    return next(_nodes_of_type(value, node_type), None) is not None


def _set_figure_image(figure: PandocNode, target: str, alt: str) -> None:
    content = figure.get("c")
    if not isinstance(content, list) or len(content) != 3:
        raise ValueError("unsupported Pandoc Figure schema")
    content[2] = [_image_paragraph(target, alt)]


def _append_raw_latex(figure: PandocNode, source: str) -> None:
    content = figure.get("c")
    if not isinstance(content, list) or len(content) != 3:
        return
    content[2] = [_code_block(source, "latex")]


def _image_paragraph(target: str, alt: str) -> PandocNode:
    return {
        "t": "Para",
        "c": [
            {
                "t": "Image",
                "c": [
                    ["", [], []],
                    [{"t": "Str", "c": alt}],
                    [target, ""],
                ],
            }
        ],
    }


def _header(level: int, title: str) -> PandocNode:
    return {
        "t": "Header",
        "c": [level, ["", [], []], [{"t": "Str", "c": title}]],
    }


def _code_block(content: str, language: str) -> PandocNode:
    return {"t": "CodeBlock", "c": [["", [language], []], content]}
