import argparse
from pathlib import Path
from typing import Any, cast

from TexSoup import TexNode, TexSoup
from TexSoup.data import TexGroup, TexText


def _recursively_strip_whitespace(node: TexNode):
    for child in node.all:
        # If this is a TexGroup, recurse
        if isinstance(child.expr, TexGroup):
            _recursively_strip_comments(child)
            continue

        # If this is the root node or is not a text node, ignore.
        if child.parent is None or not isinstance(child.expr, TexText):
            continue

        # If this is not a whitespace node, or if the node is marked to preserve whitespace, ignore.
        content = child.expr._text
        is_whitespace = isinstance(content, str) and content.isspace()
        if not is_whitespace or child.expr.preserve_whitespace:
            continue

        # Otherwise, remove the node
        child.parent.remove(child)

    return node


def _recursively_strip_comments(node: TexNode):
    for child in node.all:
        # If this is a TexGroup, recurse
        if isinstance(child.expr, TexGroup):
            _recursively_strip_comments(child)
            continue

        # If this is the root node or is not a text node, ignore.
        if child.parent is None or not isinstance(child.expr, TexText):
            continue

        # If this is not a comment node, ignore.
        content = child.expr._text.strip()
        print(content)
        if not content.startswith("%"):
            continue

        # Otherwise, remove the node
        child.parent.remove(child)

    return node


def strip(
    node: TexNode,
    *,
    strip_comments: bool = True,
    strip_whitespace: bool = True,
):
    if strip_whitespace:
        node = _recursively_strip_whitespace(node)
    if strip_comments:
        node = _recursively_strip_comments(node)
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
