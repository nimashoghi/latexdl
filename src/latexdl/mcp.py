from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Annotated, Any

from fastmcp import Context, FastMCP
from fastmcp.experimental.sampling.handlers.openai import OpenAISamplingHandler
from mcp.types import ModelHint, ModelPreferences, TextContent

from .main import convert_arxiv_latex


def _sampling_handler_kwargs() -> dict[str, Any]:
    # Use OpenAI handler if OPENAI_API_KEY is set, otherwise nothing
    if (key := os.getenv("OPENAI_API_KEY")) is None:
        return {}

    if importlib.util.find_spec("openai") is None:
        raise ImportError(
            "The 'openai' package is required for OpenAI sampling handler. Please install it via 'pip install openai'."
        )

    if (
        sampling_handler_behavior := os.getenv("SAMPLING_HANDLER_BEHAVIOR", "fallback")
    ) not in ("fallback", "always"):
        raise ValueError(
            "Invalid SAMPLING_HANDLER_BEHAVIOR value. Must be 'fallback' or 'always'. "
            f"Got: {sampling_handler_behavior}"
        )

    from openai import Client
    from openai.types import ChatModel
    from pydantic import TypeAdapter

    default_model = TypeAdapter(ChatModel).validate_python(
        os.getenv("OPENAI_MODEL", "o3")
    )

    return {
        "sampling_handler": OpenAISamplingHandler(
            default_model=default_model,
            client=Client(
                api_key=key,
                base_url=os.getenv("OPENAI_API_BASE"),
            ),
        ),
        "sampling_handler_behavior": sampling_handler_behavior,
    }


mcp = FastMCP("latexdl", **_sampling_handler_kwargs())

# Environment variables:
# - ARXIV_CACHE_ENABLED: Enable/disable summary caching (default: "false")
# - ARXIV_CACHE_PATH: Path to the directory for summary cache. Required if caching is enabled.
# - ARXIV_ENABLE_DOWNLOAD_TOOL: Enable the 'download_paper_content' tool (default: "false")
# - ARXIV_SUMMARIZATION_PROMPT: Custom prompt for paper summarization
# - ARXIV_FALLBACK_TO_LATEX: Enable/disable fallback to LaTeX when fails (default: "true")

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


def _get_summary_cache_path() -> Path | None:
    """Check for summary cache env vars and return the path if valid."""
    cache_enabled = os.getenv("ARXIV_CACHE_ENABLED", "false").lower() in (
        "true",
        "1",
        "yes",
        "on",
    )
    if not cache_enabled:
        return None

    cache_path_str = os.getenv("ARXIV_CACHE_PATH")
    if not cache_path_str:
        raise ValueError(
            "ARXIV_CACHE_ENABLED is true, but ARXIV_CACHE_PATH is not set. "
            "Please set the cache path environment variable."
        )

    return Path(cache_path_str)


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


if os.getenv("ARXIV_ENABLE_DOWNLOAD_TOOL", "1").lower() in (
    "true",
    "1",
    "yes",
    "on",
):

    @mcp.tool(
        name="download_paper_content",
        description="Download and extract the full text content of an arXiv paper given its ID.",
    )
    async def download_paper_content(
        arxiv_id: Annotated[
            str, "ArXiv paper ID (e.g., '2103.12345' or '2103.12345v1')"
        ],
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
    name="analyze_arxiv_paper",
    description="Download an arXiv paper and ask specific questions about it using a custom prompt and a high-capability model.",
)
async def analyze_arxiv_paper(
    arxiv_id: Annotated[str, "ArXiv paper ID (e.g., '2103.12345' or '2103.12345v1')"],
    custom_prompt: Annotated[str, "Custom question or analysis prompt about the paper"],
    ctx: Context,
) -> str:
    """Download a paper and analyze it based on a custom prompt using AI.

    Args:
        arxiv_id: The arXiv ID of the paper to download and analyze
        custom_prompt: The specific question or analysis you want to perform on the paper
        ctx: MCP context for sampling

    Returns:
        An AI-generated analysis based on the custom prompt
    """
    try:
        # Download the paper content using robust method
        content = await _robust_download_paper(arxiv_id)

        # Prepare the full prompt for the AI model
        full_prompt = f"""
{custom_prompt}

---

Here is the paper content:

{content}
"""

        # Use model preferences to strongly prefer o3
        prefs = ModelPreferences(
            intelligencePriority=0.99,
            speedPriority=0.01,
            costPriority=0.01,
            hints=[ModelHint(name="github.copilot-chat/o3")],
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
        analysis = reply.text

        return analysis

    except Exception as e:
        return f"Error analyzing paper {arxiv_id}: {str(e)}"


@mcp.tool(
    name="summarize_arxiv_paper",
    description="Download an arXiv paper and generate an AI-powered summary using a high-capability model.",
)
async def summarize_arxiv_paper(
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
        cache_dir = _get_summary_cache_path()
        cache_file: Path | None = None

        if cache_dir:
            # Sanitize arxiv_id to create a valid filename
            sanitized_id = "".join(c for c in arxiv_id if c.isalnum() or c in "._-")
            cache_file = cache_dir / f"{sanitized_id}.md"

            # Check if summary exists in cache
            if cache_file.is_file():
                return cache_file.read_text()

        # First, download the paper content using robust method
        content = await _robust_download_paper(arxiv_id)

        # Use environment variable or default for the prompt
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
            hints=[ModelHint(name="github.copilot-chat/o3")],
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
        summary = reply.text

        # Save the new summary to the cache if enabled
        if cache_file and cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(summary)

        return summary

    except Exception as e:
        return f"Error summarizing paper {arxiv_id}: {str(e)}"


def main():
    mcp.run()


if __name__ == "__main__":
    main()
