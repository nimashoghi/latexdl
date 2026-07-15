from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParsedCitation:
    id: str
    title: str
    authors: list[str]


@dataclass(frozen=True, kw_only=True)
class ArxivMetadata:
    """Structured container for arxiv paper metadata.

    Contains essential metadata fields like title, authors, published date, etc.
    """

    title: str
    authors: list[str]
    published: datetime.date | None
    summary: str
    entry_id: str
    pdf_url: str | None
    citations: list[ParsedCitation] | None = None

    @property
    def authors_str(self) -> str:
        """Return a string representation of the authors."""
        return ", ".join(self.authors)

    @property
    def published_str(self) -> str:
        """Return a string representation of the published date."""
        return (
            self.published.strftime("%B %d, %Y") if self.published else "Unknown date"
        )

    def format_for_markdown(self) -> str:
        """Format the metadata as markdown.

        Returns:
            A string containing the formatted metadata in markdown format.
        """
        abstract_str = "\n".join(f"> {line}" for line in self.summary.splitlines())
        return (
            f"# {self.title}\n\n"
            f"**Authors:** {self.authors_str}  \n"
            f"**Published:** {self.published_str}  \n"
            f"**Abstract:**\n{abstract_str}  \n\n"
            f"---\n\n"
        )

    def format_for_latex(self) -> str:
        """Format the metadata as LaTeX.

        Returns:
            A string containing the formatted metadata in LaTeX format.
        """
        abstract_str = "\n".join(f"%\t{line}" for line in self.summary.splitlines())
        return (
            f"% {self.title}\n"
            f"% Authors: {self.authors_str}\n"
            f"% Published: {self.published_str}\n"
            f"% Abstract:\n{abstract_str}\n\n"
            f"%% ----------------------------------------------------------------\n\n"
        )

    def _arxiv_id_full(self):
        return self.entry_id.rsplit("/", 1)[-1]
