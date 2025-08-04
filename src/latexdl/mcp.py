from __future__ import annotations

import os
from typing import Annotated

from fastmcp import Context, FastMCP
from mcp.types import ModelHint, ModelPreferences, TextContent

from .main import convert_arxiv_latex

mcp = FastMCP("ArxivDL")

# Environment variables:
# - ARXIV_SUMMARIZATION_PROMPT: Custom prompt for paper summarization
# - ARXIV_FALLBACK_TO_LATEX: Enable/disable fallback to LaTeX when markdown fails (default: "true")

# Default summarization prompt
DEFAULT_SUMMARIZATION_PROMPT = """
Please provide a comprehensive summary of this research paper. Include:

1. **Main Contribution**: What is the primary contribution or finding of this work?
2. **Problem Statement**: What problem does this paper address?
3. **Methodology**: What approach or methods did the authors use?
4. **Key Results**: What are the main experimental results or theoretical findings?
5. **Significance**: Why is this work important? What impact might it have?
6. **Limitations**: What are the limitations or potential weaknesses of this work?

Please keep the summary concise but thorough, suitable for someone who wants to quickly understand the paper's essence.
"""


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


@mcp.tool(
    name="summarize_paper",
    description="Download an arXiv paper and generate an AI-powered summary using a high-capability model. Optionally accepts a custom prompt to focus the summary on specific aspects or questions.",
)
async def summarize_paper(
    arxiv_id: Annotated[str, "ArXiv paper ID (e.g., '2103.12345' or '2103.12345v1')"],
    ctx: Context,
    custom_prompt: Annotated[
        str | None,
        "Optional custom prompt for summarization. If provided, this will be used instead of the default prompt. You can include specific questions or focus areas for the summary.",
    ] = None,
) -> str:
    """Download a paper and generate a comprehensive summary using AI.

    Args:
        arxiv_id: The arXiv ID of the paper to download and summarize
        ctx: MCP context for sampling
        custom_prompt: Optional custom prompt to override the default summarization prompt.
                      Use this to ask specific questions or focus on particular aspects of the paper.

    Returns:
        An AI-generated summary of the paper
    """
    try:
        # First, download the paper content using robust method
        content = await _robust_download_paper(arxiv_id)

        # Use custom prompt if provided, otherwise use environment variable or default
        if custom_prompt is not None:
            summarization_prompt = custom_prompt
        else:
            summarization_prompt = os.getenv(
                "ARXIV_SUMMARIZATION_PROMPT", DEFAULT_SUMMARIZATION_PROMPT
            )

        # Prepare the full prompt for the AI model
        full_prompt = f"""
{summarization_prompt}

---

Here is the paper content:

{content}
"""

        # Use model preferences to strongly prefer o3
        prefs = ModelPreferences(
            intelligencePriority=0.99,
            speedPriority=0.01,
            costPriority=0.01,
            hints=[ModelHint(name="o3")],
        )

        # Sample from the AI model
        reply = await ctx.sample(
            messages=full_prompt,
            max_tokens=16384,
            temperature=0.2,
            model_preferences=prefs,
        )

        # Extract text from the response
        assert isinstance(reply, TextContent), "Expected a TextContent response"
        return reply.text

    except Exception as e:
        return f"Error summarizing paper {arxiv_id}: {str(e)}"


def main():
    mcp.run()


if __name__ == "__main__":
    main()
