from __future__ import annotations

import os
from typing import Annotated

from fastmcp import FastMCP

from .main import convert_arxiv_latex

mcp = FastMCP("latexdl")

# Environment variables:
# - ARXIV_FALLBACK_TO_LATEX: Enable/disable fallback to LaTeX when markdown conversion fails (default: "true")


def _should_fallback_to_latex() -> bool:
    """Check if we should fallback to LaTeX when markdown conversion fails.

    Returns:
        True if fallback is enabled (default), False otherwise
    """
    fallback_env = os.getenv("ARXIV_FALLBACK_TO_LATEX", "true").lower()
    return fallback_env in ("true", "1", "yes", "on")


async def _robust_download_paper(arxiv_id: str) -> str:
    """Download paper with robust fallback behavior.

    Tries to convert to markdown first, falls back to LaTeX if markdown conversion fails
    and fallback is enabled via environment variable.

    Args:
        arxiv_id: The arXiv ID of the paper to download

    Returns:
        The paper content (markdown if successful, LaTeX if fallback enabled)

    Raises:
        Exception: If both markdown and LaTeX downloads fail, or if fallback is disabled
    """
    try:
        # First, try to convert to markdown
        content, metadata = convert_arxiv_latex(
            arxiv_id,
            markdown=True,
            include_bibliography=True,
            include_metadata=True,
            use_cache=True,
        )
        return content
    except Exception as markdown_error:
        # If markdown conversion fails and fallback is enabled, try LaTeX
        if _should_fallback_to_latex():
            try:
                content, metadata = convert_arxiv_latex(
                    arxiv_id,
                    markdown=False,  # Get raw LaTeX
                    include_bibliography=True,
                    include_metadata=True,
                    use_cache=True,
                )
                return content
            except Exception as latex_error:
                # Both conversions failed
                raise Exception(
                    f"Both markdown and LaTeX conversion failed. "
                    f"Markdown error: {markdown_error}. LaTeX error: {latex_error}"
                )
        else:
            # Fallback is disabled, re-raise the original markdown error
            raise markdown_error


@mcp.tool(
    name="download_paper_content",
    description="Download and extract the full text content of an arXiv paper given its ID.",
)
async def download_paper_content(
    arxiv_id: Annotated[str, "ArXiv paper ID (e.g., '2103.12345' or '2103.12345v1')"],
) -> str:
    """Download the full content of an arXiv paper.

    Args:
        arxiv_id: The arXiv ID of the paper to download

    Returns:
        The full text content of the paper (markdown if possible, LaTeX if fallback enabled)
    """
    try:
        return await _robust_download_paper(arxiv_id)
    except Exception as e:
        return f"Error downloading paper {arxiv_id}: {str(e)}"


def main():
    mcp.run()


if __name__ == "__main__":
    main()
