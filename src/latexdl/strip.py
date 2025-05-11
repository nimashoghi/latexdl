from __future__ import annotations

import concurrent.futures
import importlib.util
import logging

log = logging.getLogger(__name__)


def check_pandoc_installed() -> bool:
    """Check if pandoc is installed on the system."""
    return importlib.util.find_spec("pypandoc") is not None


def _run_pypandoc_conversion(
    content_arg: str, format_arg: str, to_arg: str, extra_args_arg: list[str]
) -> str:
    """Run pypandoc.convert_text in a manner suitable for ThreadPoolExecutor."""
    import pypandoc  # Import here as it's used after the check in strip()

    return pypandoc.convert_text(
        source=content_arg,
        format=format_arg,
        to=to_arg,
        extra_args=extra_args_arg,
    )


def strip(content: str, timeout: int = 60) -> str:
    """Strips LaTeX content to plain text using pandoc.

    Args:
        content: The LaTeX content to strip.
        timeout: Maximum execution time for pandoc in seconds. Defaults to 60 seconds (1 minute).

    Returns:
        The stripped plain text content.

    Raises:
        RuntimeError: If Pypandoc is not installed or fails to process the content.
        concurrent.futures.TimeoutError: If the Pypandoc process times out.
    """
    # Make sure that pypandoc is installed
    if not check_pandoc_installed():
        raise RuntimeError(
            "Pypandoc is not installed. Please install it to use this function."
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            _run_pypandoc_conversion,
            content,
            "latex-latex_macros",
            "markdown",
            ["--wrap=none"],
        )

        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            log.error(f"Pypandoc operation timed out after {timeout} seconds")
            future.cancel()  # Attempt to cancel the underlying operation
            raise
        except Exception as e:
            # This will catch errors from pypandoc.convert_text itself
            log.error(f"Pypandoc conversion failed: {e}")
            raise RuntimeError(
                f"Failed to strip LaTeX content using Pypandoc: {e}"
            ) from e
