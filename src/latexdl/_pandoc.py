import os
import subprocess
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def _working_directory(path: Path):
    """Temporarily change working directory."""
    prev_cwd = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev_cwd)


def convert_latex_to_markdown(input_file: Path, format: str = "markdown") -> str:
    """
    Convert LaTeX to Markdown or plain text using pandoc.

    Args:
        input_file: Path to the LaTeX file
        format: Output format ("markdown" or "plain")

    Returns:
        str: Converted content

    Raises:
        subprocess.CalledProcessError: If pandoc conversion fails
    """
    try:
        # Change to the input file's directory so pandoc can find includes
        with _working_directory(input_file.parent):
            # For plain text, we use the plain format
            # For markdown, we use markdown
            output_format = "plain" if format == "plain" else "markdown"

            # Note: RTS options need to be at the start
            command = ["pandoc"]
            rts_options = ["+RTS", "-K500M", "-RTS"]  # Increased to 500MB to be safe
            pandoc_options = [
                "-f",
                "latex",
                "-t",
                output_format,
                # "--wrap=none",
                # "--strip-comments",
                input_file.name,
            ]

            result = subprocess.run(
                command + rts_options + pandoc_options,
                capture_output=True,
                text=True,
                check=True,
                env={"GHCRTS": "-K500M"},  # Also set via environment variable
            )
            return result.stdout
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Pandoc conversion failed: {e.stderr}") from e
