import argparse
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from TexSoup import TexNode, TexSoup
from TexSoup.data import TexCmd, TexEnv, TexExpr, TexGroup, TexNamedEnv, TexText
from TexSoup.utils import TC, Token


def _recurse(
    node: TexExpr,
    child_fn: Callable[[TexExpr, TexExpr], TexExpr | None],
):
    for child in node.all:
        # If the child isn't a TexExpr, this is a leaf node. Continue.
        if not isinstance(child, TexExpr):
            continue

        # Call the child function. If it returns None, continue.
        if (child := child_fn(child, node)) is None:
            continue

        # Recurse on all the children
        _recurse(child, child_fn)

    return node


def _strip_whitespace(node: TexExpr):
    def child_fn(child: TexExpr, parent: TexExpr):
        # If this is not a text node, ignore.
        if not isinstance(child, TexText):
            return child

        # If this is not a whitespace node, or if the node is marked to preserve whitespace, ignore.
        content = child._text
        is_whitespace = isinstance(content, str) and content.isspace()
        if not is_whitespace or child.preserve_whitespace:
            return child

        # Otherwise, remove the node
        parent.remove(child)
        return None

    return _recurse(node, child_fn)


def _strip_comments(node: TexExpr):
    def child_fn(child: TexExpr, parent: TexExpr):
        # If this is not a text node, ignore.
        if not isinstance(child, TexText):
            return child

        # If this is not a comment node, ignore.
        content = child._text
        if not isinstance(content, Token) or content.category != TC.Comment:
            return child

        # Otherwise, remove the node
        parent.remove(child)
        return None

    return _recurse(node, child_fn)


def _strip_clutter(node: TexExpr):
    CLUTTER_ENVS = {
        "figure",
        "figure*",
        "table",
        "table*",
        "tabular",
        "tabular*",
        "tabularx",
        "tabu",
        "longtable",
        "wraptable",
        "wrapfigure",
        "wrapfloat",
        "wrapfloat*",
        "wrapfigure*",
        "wraptable*",
        # tikz
        "tikzpicture",
        "pgfpicture",
    }

    def child_fn(child: TexExpr, parent: TexExpr):
        # Remove clutter environments, e.g., figures and tables
        if isinstance(child, TexNamedEnv) and child.name in CLUTTER_ENVS:
            print(f"Removing {child} environment")
            parent.remove(child)
            return None

        # Remove custom command declarations, e.g., \newcommand, \renewcommand, \def, etc.
        if isinstance(child, TexCmd) and child.name in {
            "newcommand",
            "renewcommand",
            "def",
        }:
            print(f"Removing {child} command")
            parent.remove(child)
            return None

        return child

    return _recurse(node, child_fn)


def strip(
    node: TexNode,
    *,
    strip_comments: bool = True,
    strip_whitespace: bool = True,
    strip_clutter: bool = True,
):
    if strip_whitespace:
        node = TexNode(_strip_whitespace(node.expr))
    if strip_comments:
        node = TexNode(_strip_comments(node.expr))
    if strip_clutter:
        node = TexNode(_strip_clutter(node.expr))
    return node


def main():
    parser = argparse.ArgumentParser(description="Expand LaTeX files")
    parser.add_argument("input", help="Input LaTeX file", type=Path)
    parser.add_argument(
        "--comments",
        help="Strip comments",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--whitespace",
        help="Strip whitespace",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--output",
        help="Output LaTeX file. If not provided, the output is printed to stdout.",
        type=Path,
        required=False,
    )
    args = parser.parse_args()

    # Resolve the input file
    input: Path = args.input
    resolved = repr(
        strip(
            TexSoup(input.read_text(encoding="utf-8")),
            strip_comments=args.strip_comments,
            strip_whitespace=args.strip_whitespace,
        )
    )

    # Write the output
    if args.output:
        args.output.write_text(resolved, encoding="utf-8")
    else:
        print(resolved)


if __name__ == "__main__":
    main()
