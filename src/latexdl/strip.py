import argparse
import enum
import logging
import sys
from collections.abc import Callable
from pathlib import Path

from pylatexenc.latexwalker import (
    LatexCharsNode,
    LatexCommentNode,
    LatexEnvironmentNode,
    LatexGroupNode,
    LatexMacroNode,
    LatexNode,
    LatexWalker,
    ParsingState,
)


class RecurseAction(enum.Enum):
    CONTINUE = enum.auto()
    SKIP = enum.auto()
    REMOVE = enum.auto()


def _recurse(
    node: LatexNode,
    child_fn: Callable[[LatexNode, LatexNode | None], RecurseAction],
    parent: LatexNode | None = None,
) -> LatexNode | None:
    try:
        # Process current node
        action = child_fn(node, parent)
        if action == RecurseAction.REMOVE:
            return None
        elif action == RecurseAction.SKIP:
            return node

        # Recurse based on node type
        if isinstance(node, LatexEnvironmentNode):
            new_nodelist = _process_nodelist(node.nodelist, child_fn, node)
            if new_nodelist:
                node.nodelist = new_nodelist
        elif isinstance(node, LatexMacroNode):
            if node.nodeargd and node.nodeargd.argnlist:
                new_argnlist = [
                    _process_nodelist(arg, child_fn, node)
                    if isinstance(arg, list)
                    else _recurse(arg, child_fn, node)
                    for arg in node.nodeargd.argnlist
                ]
                node.nodeargd.argnlist = [
                    arg for arg in new_argnlist if arg is not None
                ]
        elif isinstance(node, LatexGroupNode):
            new_nodelist = _process_nodelist(node.nodelist, child_fn, node)
            if new_nodelist:
                node.nodelist = new_nodelist

        return node
    except Exception as e:
        logging.error(f"Error while recursing through {node}. Skipping. Error: {e}")
        return node


def _process_nodelist(
    nodelist: list[LatexNode],
    child_fn: Callable[[LatexNode, LatexNode | None], RecurseAction],
    parent: LatexNode | None = None,
) -> list[LatexNode]:
    result = []
    for node in nodelist:
        processed = _recurse(node, child_fn, parent)
        if processed is not None:
            result.append(processed)
    return result


def _strip_whitespace(node: LatexNode) -> LatexNode | None:
    def child_fn(child: LatexNode, parent: LatexNode | None) -> RecurseAction:
        if isinstance(child, LatexCharsNode):
            # Only remove if the node is pure whitespace
            if child.chars.isspace():
                return RecurseAction.REMOVE
            # Otherwise, normalize whitespace
            child.chars = " ".join(child.chars.split())
        return RecurseAction.CONTINUE

    return _recurse(node, child_fn)


def _strip_comments(node: LatexNode) -> LatexNode | None:
    def child_fn(child: LatexNode, parent: LatexNode | None) -> RecurseAction:
        if isinstance(child, LatexCommentNode):
            return RecurseAction.REMOVE
        return RecurseAction.CONTINUE

    return _recurse(node, child_fn)


def _strip_clutter(node: LatexNode) -> LatexNode | None:
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
        "center",
        "flushleft",
        "flushright",
        "tikzpicture",
        "pgfpicture",
    }

    CLUTTER_COMMANDS = {
        "newcommand",
        "renewcommand",
        "def",
    }

    def child_fn(child: LatexNode, parent: LatexNode | None) -> RecurseAction:
        if isinstance(child, LatexEnvironmentNode) and child.envname in CLUTTER_ENVS:
            # Remove the entire environment including its contents
            return RecurseAction.REMOVE
        if isinstance(child, LatexMacroNode) and child.macroname in CLUTTER_COMMANDS:
            # Remove the entire macro including its arguments
            return RecurseAction.REMOVE
            # Remove the entire macro including its arguments
            return RecurseAction.REMOVE
        return RecurseAction.CONTINUE

    return _recurse(node, child_fn)


def _seek_to_document_node(node: LatexNode) -> LatexNode | None:
    if isinstance(node, LatexEnvironmentNode) and node.envname == "document":
        return node

    if isinstance(node, (LatexEnvironmentNode, LatexGroupNode)):
        for child in node.nodelist:
            result = _seek_to_document_node(child)
            if result:
                return result

    return None


def strip(
    content: str,
    *,
    strip_comments: bool = True,
    strip_whitespace: bool = True,
    strip_clutter: bool = True,
    seek_to_document_node: bool = True,
) -> str:
    """
    Strip unnecessary elements from LaTeX content while preserving LaTeX structure.

    Args:
        content: Input LaTeX content
        strip_comments: Whether to remove comments
        strip_whitespace: Whether to normalize whitespace
        strip_clutter: Whether to remove clutter (figures, tables, etc)
        seek_to_document_node: Whether to extract only the document environment content

    Returns:
        Stripped LaTeX content as a string
    """
    # Parse the LaTeX content
    walker = LatexWalker(content)
    nodes, _, _ = walker.get_latex_nodes()

    if not nodes:
        return content

    # Create a root node to process everything
    root = LatexGroupNode(parsing_state=ParsingState(), nodelist=nodes)

    # Apply the transformations
    if strip_comments:
        root = _strip_comments(root) or root
    if strip_whitespace:
        root = _strip_whitespace(root) or root
    if strip_clutter:
        root = _strip_clutter(root) or root

    if seek_to_document_node and (document_node := _seek_to_document_node(root)):
        root = document_node

    # Convert back to string preserving LaTeX structure
    return root.latex_verbatim()


def main():
    parser = argparse.ArgumentParser(description="Strip LaTeX files")
    parser.add_argument(
        "--input",
        help="Input LaTeX file. If not provided, stdin is used.",
        type=Path,
        required=False,
    )
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
        help="Output LaTeX file. If not provided, output is printed to stdout.",
        type=Path,
        required=False,
    )
    args = parser.parse_args()

    # Read input
    content = args.input.read_text(encoding="utf-8") if args.input else sys.stdin.read()

    # Process the content
    result = strip(
        content,
        strip_comments=args.comments,
        strip_whitespace=args.whitespace,
        strip_clutter=args.strip_clutter,
        seek_to_document_node=args.seek_to_document,
    )

    # Write output
    if args.output:
        args.output.write_text(result, encoding="utf-8")
    else:
        print(result)
