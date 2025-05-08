from __future__ import annotations

import logging

from ._types import ArxivMetadata

# Try importing the arxiv package, with a helpful error message if not found
try:
    import arxiv
except ImportError:
    raise ImportError(
        "The 'arxiv' package is required for metadata extraction. "
        "Please install it with 'pip install arxiv'"
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

    Raises:
        arxiv.ArxivError: If there's an error communicating with the arXiv API
    """
    try:
        # The arxiv ID might have a version suffix (vN), remove it if present
        # to ensure we get the latest version
        base_id = arxiv_id.split("v")[0] if "v" in arxiv_id else arxiv_id

        # Query the arXiv API
        search = arxiv.Search(id_list=[base_id], max_results=1)

        # Get the first result
        results = list(search.results())
        if not results:
            logging.warning(f"No metadata found for arXiv ID: {arxiv_id}")
            return None

        paper = results[0]

        # Extract and structure the metadata
        metadata = ArxivMetadata(
            title=paper.title,
            authors=[author.name for author in paper.authors],
            published=paper.published.date() if paper.published else None,
            summary=paper.summary,
            entry_id=paper.entry_id,
            pdf_url=paper.pdf_url,
        )

        return metadata

    except Exception as e:
        logging.warning(f"Error fetching metadata for arXiv ID {arxiv_id}: {e}")
        return None
