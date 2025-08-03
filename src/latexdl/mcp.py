from __future__ import annotations

import os
from typing import Annotated

from fastmcp import Context, FastMCP
from mcp.types import ModelHint, ModelPreferences

from .main import convert_arxiv_latex

mcp = FastMCP("ArxivDL")

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
        The full text content of the paper in markdown format
    """
    try:
        # Convert to markdown with all metadata and bibliography
        content, metadata = convert_arxiv_latex(
            arxiv_id,
            markdown=True,
            include_bibliography=True,
            include_metadata=True,
            use_cache=True,
        )

        return content
    except Exception as e:
        return f"Error downloading paper {arxiv_id}: {str(e)}"


@mcp.tool(
    name="summarize_paper",
    description="Download an arXiv paper and generate an AI-powered summary using a high-capability model.",
)
async def summarize_paper(
    arxiv_id: Annotated[str, "ArXiv paper ID (e.g., '2103.12345' or '2103.12345v1')"],
    ctx: Context,
) -> str:
    """Download a paper and generate a comprehensive summary using AI.

    Args:
        arxiv_id: The arXiv ID of the paper to download and summarize
        ctx: MCP context for sampling

    Returns:
        An AI-generated summary of the paper
    """
    try:
        # First, download the paper content
        content, metadata = convert_arxiv_latex(
            arxiv_id,
            markdown=True,
            include_bibliography=True,
            include_metadata=True,
            use_cache=True,
        )

        # Get the summarization prompt from environment or use default
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
        return reply.text  # type: ignore

    except Exception as e:
        return f"Error summarizing paper {arxiv_id}: {str(e)}"


def main():
    mcp.run()


if __name__ == "__main__":
    main()
