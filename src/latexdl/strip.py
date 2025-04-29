from __future__ import annotations

import logging
import subprocess


def check_pandoc_installed() -> bool:
    """Check if pandoc is installed on the system."""
    try:
        subprocess.run(["pandoc", "--version"], check=True, stdout=subprocess.PIPE)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def strip(content: str) -> str:
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
        )

        plain_text = result.stdout.decode("utf-8")
        return plain_text
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode("utf-8") if e.stderr else "Unknown error"
        logging.error(f"Failed to strip LaTeX content: {error_msg}")
        raise RuntimeError(f"Failed to strip LaTeX content: {error_msg}")
