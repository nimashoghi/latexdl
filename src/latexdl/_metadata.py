from __future__ import annotations

import logging
from urllib.parse import urlparse

from ._types import ArxivMetadata

# Try importing the arxiv package, with a helpful error message if not found
try:
    import arxiv
except ImportError:
    raise ImportError(
        "The 'arxiv' package is required for metadata extraction. "
        "Please install it with 'pip install arxiv'"
    )

log = logging.getLogger(__name__)

_ARXIV_API_QUERY_URL_FORMATS = (
    arxiv.Client.query_url_format,
    "https://arxiv.org/api/query?{}",
)


def fetch_arxiv_metadata(arxiv_id: str) -> ArxivMetadata | None:
    """Fetch metadata for an arXiv paper.

    Uses the arxiv API to retrieve paper metadata including title, authors,
    and publication date.

    Args:
        arxiv_id: The arXiv ID to fetch metadata for (e.g., "2103.12345")

    Returns:
        An ArxivMetadata object containing the paper metadata, or None if
        the paper could not be found or an error occurred.

    This tries the arxiv package default API host first, then retries against
    regular arxiv.org if that host is unavailable or rate limited.
    """
    # The arxiv ID might have a version suffix (vN), remove it if present
    # to ensure we get the latest version
    base_id = arxiv_id.split("v")[0] if "v" in arxiv_id else arxiv_id

    last_error: Exception | None = None
    for query_url_format in _ARXIV_API_QUERY_URL_FORMATS:
        try:
            paper = _fetch_arxiv_result(base_id, query_url_format)
        except Exception as e:
            last_error = e
            log.info(
                "Error fetching metadata for arXiv ID %s from %s: %s",
                arxiv_id,
                _query_url_hostname(query_url_format),
                e,
            )
            continue

        if paper is None:
            log.warning(f"No metadata found for arXiv ID: {arxiv_id}")
            return None

        return ArxivMetadata(
            title=paper.title,
            authors=[author.name for author in paper.authors],
            published=paper.published.date() if paper.published else None,
            summary=paper.summary,
            entry_id=paper.entry_id,
            pdf_url=paper.pdf_url,
        )

    log.warning(f"Error fetching metadata for arXiv ID {arxiv_id}: {last_error}")
    return None


def _fetch_arxiv_result(arxiv_id: str, query_url_format: str) -> arxiv.Result | None:
    search = arxiv.Search(id_list=[arxiv_id], max_results=1)
    client = arxiv.Client(page_size=1)
    client.query_url_format = query_url_format
    results = list(client.results(search))
    return results[0] if results else None


def _query_url_hostname(query_url_format: str) -> str:
    return urlparse(query_url_format).netloc
