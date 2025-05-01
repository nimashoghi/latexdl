from __future__ import annotations

import logging
import subprocess

log = logging.getLogger(__name__)


def check_pandoc_installed() -> bool:
    """Check if pandoc is installed on the system."""
    try:
        subprocess.run(["pandoc", "--version"], check=True, stdout=subprocess.PIPE)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def strip(content: str, timeout: int = 60) -> str:
    """Strips LaTeX content to plain text using pandoc.

    Args:
        content: The LaTeX content to strip.
        timeout: Maximum execution time for pandoc in seconds. Defaults to 60 seconds (1 minute).

    Returns:
        The stripped plain text content.

    Raises:
        RuntimeError: If pandoc is not installed or fails to process the content.
        subprocess.TimeoutExpired: If the pandoc process times out.
    """
    # Make sure that pandoc is installed
    if not check_pandoc_installed():
        raise RuntimeError(
            "Pandoc is not installed. Please install it to use this function."
        )

    # Use pandoc to convert LaTeX to plain text.
    # Our command is as follows: `pandoc --wrap=none -f latex -t markdown`
    # The stdin should be the LaTeX content, and the stdout will be the plain text.
    try:
        result = subprocess.run(
            ["pandoc", "--wrap=none", "-f", "latex", "-t", "markdown"],
            input=content.encode("utf-8"),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )

        plain_text = result.stdout.decode("utf-8")
        return plain_text
    except subprocess.TimeoutExpired:
        log.error(f"Pandoc process timed out after {timeout} seconds")
        raise
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode("utf-8") if e.stderr else "Unknown error"
        raise RuntimeError(f"Failed to strip LaTeX content: {error_msg}")
