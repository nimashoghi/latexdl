from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ._types import ArxivMetadata


class ConversionStatus(str, Enum):
    """Completeness state for a conversion bundle."""

    COMPLETE = "complete"
    PARTIAL = "partial"


class DiagnosticLevel(str, Enum):
    """Severity attached to a conversion diagnostic."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class Diagnostic(BaseModel):
    """A structured, machine-readable conversion diagnostic."""

    model_config = ConfigDict(frozen=True)

    level: DiagnosticLevel
    code: str
    message: str
    source: str | None = None


class AssetRecord(BaseModel):
    """Provenance for one asset referenced by the generated Markdown."""

    model_config = ConfigDict(frozen=True)

    source: str
    output: str
    media_type: str
    sha256: str
    raw_output: str | None = None
    generated: bool = False


class ConversionRequest(BaseModel):
    """Options for one arXiv-to-Markdown bundle conversion."""

    model_config = ConfigDict(frozen=True)

    paper: str
    output_dir: Path
    cache_dir: Path | None = None
    use_cache: bool = True
    force: bool = False
    include_metadata: bool = True
    include_bibliography: bool = True
    keep_comments: bool = False
    preserve_macros: bool = False
    timeout_seconds: int = 120
    render_dpi: int = 180

    @field_validator("timeout_seconds", "render_dpi")
    @classmethod
    def _must_be_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be positive")
        return value


class ConversionReport(BaseModel):
    """Completeness, provenance, and diagnostics for a generated bundle."""

    model_config = ConfigDict(frozen=True)

    schema_version: int = 2
    latexdl_version: str
    status: ConversionStatus
    arxiv_id: str
    source_version: str
    source_sha256: str
    cache_key: str
    figures_expected: int
    figures_recovered: int
    tables_expected: int
    tables_recovered: int
    citations_expected: int
    citations_preserved: int
    math_expected: int
    math_preserved: int
    options: dict[str, str | int | bool] = Field(default_factory=dict)
    assets: list[AssetRecord] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    tools: dict[str, str] = Field(default_factory=dict)

    @property
    def complete(self) -> bool:
        """Return whether every required conversion invariant passed."""
        return self.status is ConversionStatus.COMPLETE


class ConversionResult(BaseModel):
    """Paths and structured metadata for a completed conversion attempt."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    bundle_dir: Path
    paper_path: Path
    report_path: Path
    metadata: ArxivMetadata | None
    report: ConversionReport
