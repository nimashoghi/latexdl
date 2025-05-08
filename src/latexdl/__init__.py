"""
LatexDL: A tool for downloading and processing arXiv LaTeX source files.

This package provides functionality to download, extract, expand, and optionally convert
LaTeX files from arXiv to Markdown.
"""

from __future__ import annotations

from ._types import ArxivMetadata as ArxivMetadata
from .main import batch_convert_arxiv_papers as batch_convert_arxiv_papers
from .main import convert_arxiv_latex as convert_arxiv_latex
from .main import download_arxiv_source as download_arxiv_source

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
