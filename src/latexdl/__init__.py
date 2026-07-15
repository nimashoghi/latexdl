"""Convert arXiv LaTeX sources into complete, auditable Markdown bundles."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from ._types import ArxivMetadata as ArxivMetadata
from .converter import convert_arxiv as convert_arxiv
from .converter import convert_many as convert_many
from .models import AssetRecord as AssetRecord
from .models import ConversionReport as ConversionReport
from .models import ConversionRequest as ConversionRequest
from .models import ConversionResult as ConversionResult
from .models import ConversionStatus as ConversionStatus
from .models import Diagnostic as Diagnostic
from .models import DiagnosticLevel as DiagnosticLevel

try:
    __version__ = version(__name__)
except PackageNotFoundError:
    __version__ = "unknown"

__all__ = [
    "ArxivMetadata",
    "AssetRecord",
    "ConversionReport",
    "ConversionRequest",
    "ConversionResult",
    "ConversionStatus",
    "Diagnostic",
    "DiagnosticLevel",
    "convert_arxiv",
    "convert_many",
]
