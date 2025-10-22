from __future__ import annotations

import importlib.util
import re
import xml.etree.ElementTree as ET
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

from .main import convert_arxiv_latex, robust_download_paper

mcp = FastMCP("latexdl")

# Environment variables:
# - ARXIV_FALLBACK_TO_LATEX: Enable/disable fallback to LaTeX when markdown conversion fails (default: "true")


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


def _parse_latex_hierarchy(latex_text: str) -> list[dict[str, Any]]:
    """Parse LaTeX section commands into a hierarchical structure.

    Args:
        latex_text: The LaTeX content to parse

    Returns:
        A list of root-level sections, each with potential nested children
    """
    # Map LaTeX section commands to levels
    section_levels = {
        "part": 0,
        "chapter": 1,
        "section": 2,
        "subsection": 3,
        "subsubsection": 4,
        "paragraph": 5,
        "subparagraph": 6,
    }

    # Pattern to match section commands: \section{title} or \section*{title}
    section_pattern = re.compile(
        r"\\(part|chapter|section|subsection|subsubsection|paragraph|subparagraph)\*?\{([^}]+)\}",
        re.MULTILINE,
    )

    sections = [
        {
            "level": section_levels[match.group(1)],
            "title": match.group(2).strip(),
        }
        for match in section_pattern.finditer(latex_text)
    ]

    if not sections:
        return []

    # Build hierarchical structure
    root: list[dict[str, Any]] = []
    stack: list[dict[str, Any]] = []

    for section in sections:
        node = {
            "level": section["level"],
            "title": section["title"],
            "children": [],
        }

        # Find the correct parent by popping from stack until we find appropriate level
        while stack and stack[-1]["level"] >= section["level"]:
            stack.pop()

        if not stack:
            # This is a root-level section
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
        return await robust_download_paper(arxiv_id, include_bibliography)
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
        # Try markdown first
        try:
            content, metadata = convert_arxiv_latex(
                arxiv_id,
                markdown=True,
                include_bibliography=True,
                include_metadata=True,
                use_cache=True,
            )
            tree = _parse_markdown_hierarchy(content)
        except Exception:
            # Fallback to LaTeX parsing
            content, metadata = convert_arxiv_latex(
                arxiv_id,
                markdown=False,
                include_bibliography=True,
                include_metadata=True,
                use_cache=True,
            )
            tree = _parse_latex_hierarchy(content)

        # Convert to XML
        xml_str = _tree_to_xml(tree, arxiv_id)

        return xml_str

    except Exception as e:
        return f"Error extracting paper structure for {arxiv_id}: {str(e)}"


def main():
    mcp.run()


if __name__ == "__main__":
    main()
