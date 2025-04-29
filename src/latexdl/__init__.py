"""
LatexDL: A tool for downloading and processing arXiv LaTeX source files.

This package provides functionality to download, extract, expand, and optionally convert
LaTeX files from arXiv to Markdown.
"""

from __future__ import annotations
try:
    from importlib.metadata import PackageNotFoundError, version
except ImportError:
    # For Python <3.8
    from importlib_metadata import (  # pyright: ignore[reportMissingImports]
        PackageNotFoundError,
        version,
    )

try:
    __version__ = version(__name__)
except PackageNotFoundError:
    __version__ = "unknown"
