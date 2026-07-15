from __future__ import annotations

import asyncio
import importlib.util
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Annotated, Any

_OPTIONAL_MCP_PACKAGES = {
    "fastmcp": "latexdl[mcp]",
    "pydantic_ai": "latexdl[mcp]",
    "openai": "latexdl[mcp]",
}

# Fail fast with guidance if optional MCP dependencies are missing.
_missing_optional = [
    pkg for pkg in _OPTIONAL_MCP_PACKAGES if importlib.util.find_spec(pkg) is None
]
if _missing_optional:
    missing = ", ".join(sorted(_missing_optional))
    hint = _OPTIONAL_MCP_PACKAGES[_missing_optional[0]]
    raise ImportError(
        f"Missing optional MCP dependencies: {missing}. "
        f"Install via `pip install {hint}`."
    )

from fastmcp import FastMCP

from .converter import convert_arxiv
from .models import ConversionRequest

mcp = FastMCP("latexdl")


def _parse_markdown_hierarchy(markdown_text: str) -> list[dict[str, Any]]:
    """Parse markdown headings into a hierarchical structure.

    Args:
        markdown_text: The markdown content to parse

    Returns:
        A list of root-level sections, each with potential nested children
    """
    # Extract all heading lines with their levels
    heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
    headings = [
        {"level": len(match.group(1)), "title": match.group(2).strip()}
        for match in heading_pattern.finditer(markdown_text)
    ]

    if not headings:
        return []

    # Build hierarchical structure
    root: list[dict[str, Any]] = []
    stack: list[dict[str, Any]] = []

    for heading in headings:
        node = {
            "level": heading["level"],
            "title": heading["title"],
            "children": [],
        }

        # Find the correct parent by popping from stack until we find appropriate level
        while stack and stack[-1]["level"] >= heading["level"]:
            stack.pop()

        if not stack:
            # This is a root-level heading
            root.append(node)
        else:
            # Add as child of the last item in stack
            stack[-1]["children"].append(node)

        stack.append(node)

    return root


def _tree_to_xml(tree: list[dict[str, Any]], arxiv_id: str) -> str:
    """Convert hierarchical structure to XML string.

    Args:
        tree: The hierarchical section structure
        arxiv_id: The arXiv ID of the paper

    Returns:
        XML string representation of the structure
    """
    root = ET.Element("paper")
    root.set("arxiv_id", arxiv_id)

    def add_sections(parent_elem: ET.Element, sections: list[dict[str, Any]]) -> None:
        for section in sections:
            section_elem = ET.SubElement(parent_elem, "section")
            section_elem.set("level", str(section["level"]))
            section_elem.set("title", section["title"])

            if section["children"]:
                add_sections(section_elem, section["children"])

    add_sections(root, tree)

    # Convert to string with pretty formatting
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


@mcp.tool(
    name="read_paper",
    description="Download and extract the full text content of an arXiv paper given its ID.",
)
async def read_paper(
    arxiv_id: Annotated[str, "ArXiv paper ID (e.g., '2103.12345' or '2103.12345v1')"],
    include_bibliography: Annotated[
        bool, "Whether to include the bibliography section (default: False)"
    ] = False,
) -> str:
    """Download the full content of an arXiv paper.

    Args:
        arxiv_id: The arXiv ID of the paper to download
        include_bibliography: Whether to include the bibliography section

    Returns:
        The full text content of the paper (markdown if possible, LaTeX if fallback enabled)
    """
    try:
        return await asyncio.to_thread(
            _convert_paper_text,
            arxiv_id,
            include_bibliography,
        )
    except Exception as e:
        return f"Error downloading paper {arxiv_id}: {str(e)}"


@mcp.tool(
    name="get_paper_structure",
    description="Extract the hierarchical section structure of an arXiv paper as XML. Works for both markdown and LaTeX papers.",
)
async def get_paper_structure(
    arxiv_id: Annotated[str, "ArXiv paper ID (e.g., '2103.12345' or '2103.12345v1')"],
) -> str:
    """Get the hierarchical section structure of a paper as XML.

    This tool downloads the paper and extracts the heading hierarchy without
    the actual content text. It tries markdown first, then falls back to
    parsing LaTeX section commands if markdown conversion fails.

    Args:
        arxiv_id: The arXiv ID of the paper

    Returns:
        XML representation of the paper's section structure
    """
    try:
        content = await asyncio.to_thread(_convert_paper_text, arxiv_id, True)
        tree = _parse_markdown_hierarchy(content)

        # Convert to XML
        xml_str = _tree_to_xml(tree, arxiv_id)

        return xml_str

    except Exception as e:
        return f"Error extracting paper structure for {arxiv_id}: {str(e)}"


def _convert_paper_text(arxiv_id: str, include_bibliography: bool) -> str:
    with tempfile.TemporaryDirectory(prefix="latexdl-mcp-") as directory:
        result = convert_arxiv(
            ConversionRequest(
                paper=arxiv_id,
                output_dir=Path(directory) / "bundle",
                include_bibliography=include_bibliography,
            )
        )
        return result.paper_path.read_text(encoding="utf-8")


def main():
    mcp.run()


if __name__ == "__main__":
    main()
