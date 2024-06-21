import argparse
import enum
from collections.abc import Callable
from pathlib import Path

from TexSoup import TexNode, TexSoup
from TexSoup.data import TexCmd, TexExpr, TexNamedEnv, TexText
from TexSoup.utils import TC, Token
from typing_extensions import assert_never


class RecurseAction(enum.Enum):
    CONTINUE = enum.auto()
    SKIP = enum.auto()
    REMOVE = enum.auto()


def _recurse(
    node: TexExpr,
    child_fn: Callable[[TexExpr, TexExpr], RecurseAction],
):
    for child in node.all:
        # If the child isn't a TexExpr, this is a leaf node. Continue.
        if not isinstance(child, TexExpr):
            continue

        match child_fn(child, node):
            case RecurseAction.REMOVE:
                node.remove(child)
            case RecurseAction.SKIP:
                continue
            case RecurseAction.CONTINUE:
                _recurse(child, child_fn)
            case _action:
                assert_never(_action)

    return node


def _strip_whitespace(node: TexExpr):
    def child_fn(child: TexExpr, parent: TexExpr):
        # If this is not a text node (or the node is marked to preserve whitespace), ignore.
        if not isinstance(child, TexText) or child.preserve_whitespace:
            return RecurseAction.CONTINUE

        # If this is a whitespace node, remove it
        content = child._text
        if isinstance(content, str) and content.isspace():
            return RecurseAction.REMOVE

        return RecurseAction.CONTINUE

    return _recurse(node, child_fn)


def _strip_comments(node: TexExpr):
    def child_fn(child: TexExpr, parent: TexExpr):
        # If this is not a text node, ignore.
        if not isinstance(child, TexText):
            return RecurseAction.CONTINUE

        # If this is a comment node, remove it
        content = child._text
        if isinstance(content, Token) and content.category == TC.Comment:
            return RecurseAction.REMOVE

        return RecurseAction.CONTINUE

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
            return RecurseAction.REMOVE

        # Remove custom command declarations, e.g., \newcommand, \renewcommand, \def, etc.
        if isinstance(child, TexCmd) and child.name in {
            "newcommand",
            "renewcommand",
            "def",
        }:
            return RecurseAction.REMOVE

        return RecurseAction.CONTINUE

    return _recurse(node, child_fn)


def _seek_to_document_node(node: TexExpr):
    for child in node.all:
        # If the child isn't a TexExpr, this is a leaf node. Continue.
        if not isinstance(child, TexExpr):
            continue

        # If this is a document node, return it
        if isinstance(child, TexNamedEnv) and child.name == "document":
            return child

        # Recurse on all the children
        if (result := _seek_to_document_node(child)) is not None:
            return result

    return None


def strip(
    node: TexNode,
    *,
    strip_comments: bool = True,
    strip_whitespace: bool = True,
    strip_clutter: bool = True,
    seek_to_document_node: bool = True,
):
    if strip_whitespace:
        node = TexNode(_strip_whitespace(node.expr))
    if strip_comments:
        node = TexNode(_strip_comments(node.expr))
    if strip_clutter:
        node = TexNode(_strip_clutter(node.expr))

    if (
        seek_to_document_node
        and (document := _seek_to_document_node(node.expr)) is not None
    ):
        node = TexNode(document)
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
        "--clutter",
        help="Strip clutter",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--seek-to-document",
        help="Seek to the document node",
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
    resolved = str(
        strip(
            TexSoup(input.read_text(encoding="utf-8")),
            strip_comments=args.comments,
            strip_whitespace=args.whitespace,
            strip_clutter=args.clutter,
            seek_to_document_node=args.seek_to_document,
        )
    )

    # Write the output
    if args.output:
        args.output.write_text(resolved, encoding="utf-8")
    else:
        print(resolved)


if __name__ == "__main__":
    main()
