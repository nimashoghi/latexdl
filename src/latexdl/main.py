from __future__ import annotations

import argparse
import dataclasses
import logging
import pickle
import re
import tarfile
import urllib.parse
from pathlib import Path

import platformdirs
import requests
from tqdm import tqdm

from ._bibtex import detect_and_collect_bibtex
from ._cache import load_cache, save_cache
from ._metadata import fetch_arxiv_metadata
from ._types import ArxivMetadata
from .expand import expand_latex_file
from .strip import check_pandoc_installed, strip

log = logging.getLogger(__name__)


def _get_default_cache_dir() -> Path:
    """
    Returns a platform-specific default cache directory for storing downloaded arXiv papers.

    Returns:
        Path to the default cache directory
    """
    cache_dir = platformdirs.user_cache_path("latexdl")
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _extract_arxiv_id(package: str) -> str:
    # Approved formats (square brackets denote optional parts):
    # - arXiv ID (e.g., 2103.12345[v#])
    # - Full PDF URL (e.g., https://arxiv.org/pdf/2103.12345[v#][.pdf])
    # - Full Abs URL (e.g., https://arxiv.org/abs/2103.12345[v#])

    if package.startswith("http"):
        # Full URL
        if "pdf" in package:
            # Full PDF URL
            arxiv_id = Path(urllib.parse.urlparse(package).path).name
            if arxiv_id.endswith(".pdf"):
                arxiv_id = arxiv_id[: -len(".pdf")]
        elif "abs" in package:
            # Full Abs URL
            arxiv_id = Path(urllib.parse.urlparse(package).path).name
        else:
            raise ValueError(f"Invalid package URL format: {package}")
    else:
        # arXiv ID
        arxiv_id = package

    return arxiv_id


def download_arxiv_source(
    arxiv_id: str,
    temp_dir: Path,
    redownload_existing: bool = False,
) -> Path:
    """
    Download and extract arXiv source files.

    Args:
        arxiv_id: The arXiv ID to download
        temp_dir: Directory to store the downloaded and extracted files
        redownload_existing: Whether to redownload if archives already exist

    Returns:
        Path to the directory containing extracted files

    Raises:
        requests.HTTPError: If downloading fails
    """
    # Create a subdirectory for this paper
    output_dir = temp_dir / arxiv_id
    output_dir.mkdir(parents=True, exist_ok=True)

    fpath = temp_dir / f"{arxiv_id}.tar.gz"
    if fpath.exists() and not redownload_existing:
        log.info(f"Package {arxiv_id} already downloaded, skipping")
    else:
        url = f"https://arxiv.org/src/{arxiv_id}"
        response = requests.get(url, stream=True)
        response.raise_for_status()

        # Save the response to a file
        with fpath.open("wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

    # Extract the tarball
    with tarfile.open(fpath, "r:gz") as tar:
        tar.extractall(output_dir)

    return output_dir


def _find_main_latex_file(directory: Path) -> Path | None:
    potential_main_files: list[tuple[Path, float]] = []

    for file_path in directory.rglob("*.[tT][eE][xX]"):  # Case insensitive extension
        score = 0.0

        # Check filename
        if file_path.name.lower() in ["main.tex", "paper.tex", "article.tex"]:
            score += 5

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except UnicodeDecodeError:
            # Skip files that can't be read as UTF-8
            continue

        # Check for \documentclass
        if r"\documentclass" in content:
            score += 3

        # Check for document environment
        if r"\begin{document}" in content and r"\end{document}" in content:
            score += 4

        # Check for multiple \input or \include commands
        if len(re.findall(r"\\(input|include)", content)) > 1:
            score += 2

        # Check for bibliography
        if r"\bibliography" in content or r"\begin{thebibliography}" in content:
            score += 2

        # Consider file size
        score += min(file_path.stat().st_size / 1000, 5)  # Max 5 points for size

        potential_main_files.append((file_path, score))

    # Sort by score in descending order
    potential_main_files.sort(key=lambda x: x[1], reverse=True)

    return potential_main_files[0][0] if potential_main_files else None


def convert_arxiv_latex(
    arxiv_id_or_url: str,
    *,
    markdown: bool = False,
    redownload_existing: bool = False,
    use_cache: bool = False,
    keep_comments: bool = False,
    include_bibliography: bool = True,
    include_metadata: bool = True,
    working_dir: str | Path | None = None,
    pandoc_timeout: int = 60,
    parse_citations: bool = True,
) -> tuple[str, ArxivMetadata | None]:
    """
    Convert an arXiv paper to expanded LaTeX or markdown.

    Args:
        arxiv_id_or_url: arXiv ID or URL of the paper
        markdown: Whether to convert to markdown (requires pandoc)
        redownload_existing: Whether to redownload if archives already exist
        use_cache: Whether to use cached files if they exist
        keep_comments: Whether to keep comments in the expanded LaTeX
        include_bibliography: Whether to include bibliography content
        include_metadata: Whether to include paper metadata (title, authors, etc.)
        working_dir: Optional working directory for temporary files. If None, uses the default cache directory.
        pandoc_timeout: Maximum execution time for pandoc in seconds. Defaults to 60 seconds (1 minute).
        parse_citations: Whether to parse citations in the LaTeX file

    Returns:
        The expanded LaTeX or converted markdown content as a string, and
        the metadata as an ArxivMetadata object (if `include_metadata` is True).
        If `include_metadata` is False, the metadata will be None.

    Raises:
        RuntimeError: If the main LaTeX file cannot be found
        ValueError: If the arXiv ID format is invalid
    """
    if parse_citations and not include_bibliography:
        raise ValueError("Cannot parse citations without including bibliography")
    if parse_citations and not include_metadata:
        raise ValueError("Cannot parse citations without including metadata")

    # Extract arXiv ID
    arxiv_id = _extract_arxiv_id(arxiv_id_or_url)
    if (metadata := fetch_arxiv_metadata(arxiv_id)) is None:
        raise ValueError(
            f"Could not find paper with ID {arxiv_id} on arXiv. "
            "Please check the ID or URL."
        )

    # Create directory for downloads and extraction
    if working_dir is None:
        working_dir = _get_default_cache_dir()
        log.info(f"Using default cache directory: {working_dir}")

    temp_dir = Path(working_dir) / arxiv_id / metadata._arxiv_id_full()
    if use_cache and (cached_contents := load_cache(temp_dir)) is not None:
        log.info(f"Using cached content for {arxiv_id}")
        return cached_contents.paper_contents, cached_contents.metadata

    temp_dir.mkdir(parents=True, exist_ok=True)

    # Download and extract
    src_dir = download_arxiv_source(arxiv_id, temp_dir, redownload_existing)

    # Find main LaTeX file
    if (main_file := _find_main_latex_file(src_dir)) is None:
        raise RuntimeError(f"Could not find main LaTeX file for {arxiv_id}")

    # Expand LaTeX
    expanded_latex = expand_latex_file(main_file, keep_comments=keep_comments)

    # Convert to markdown if requested
    content = (
        strip(expanded_latex, timeout=pandoc_timeout) if markdown else expanded_latex
    )

    # Add metadata if requested
    if include_metadata:
        metadata_content = (
            metadata.format_for_markdown() if markdown else metadata.format_for_latex()
        )
        content = metadata_content + content

    # Add bibliography if requested
    if include_bibliography and (
        bib_content := detect_and_collect_bibtex(
            src_dir,
            expanded_latex,
            main_tex_path=main_file,
            markdown=markdown,
            parse_citations=parse_citations,
        )
    ):
        sep = "\n\n# References\n\n" if markdown else "\n\nREFERENCES\n\n"
        content += sep + bib_content.references_str

        if parse_citations:
            metadata = dataclasses.replace(metadata, citations=bib_content.citations)

    if use_cache:
        save_cache(temp_dir, content, metadata)
    return content, metadata


def batch_convert_arxiv_papers(
    arxiv_ids_or_urls: list[str],
    *,
    markdown: bool = False,
    redownload_existing: bool = False,
    use_cache: bool = False,
    keep_comments: bool = False,
    include_bibliography: bool = True,
    include_metadata: bool = True,
    show_progress: bool = True,
    working_dir: str | Path | None = None,
    pandoc_timeout: int = 60,
    parse_citations: bool = True,
) -> dict[str, tuple[str, ArxivMetadata | None]]:
    """
    Convert multiple arXiv papers to expanded LaTeX or markdown.

    Args:
        arxiv_ids_or_urls: List of arXiv IDs or URLs
        markdown: Whether to convert to markdown (requires pandoc)
        redownload_existing: Whether to redownload if archives already exist
        use_cache: Whether to use cached files if they exist
        keep_comments: Whether to keep comments in the expanded LaTeX
        include_bibliography: Whether to include bibliography content
        include_metadata: Whether to include paper metadata (title, authors, etc.)
        show_progress: Whether to show a progress bar
        working_dir: Optional working directory for caching files. If None, uses the default cache directory.
        pandoc_timeout: Maximum execution time for pandoc in seconds. Defaults to 60 seconds (1 minute).
        parse_citations: Whether to parse citations in the LaTeX file

    Returns:
        Dictionary mapping arXiv IDs to their converted content and metadata
    """
    results: dict[str, tuple[str, ArxivMetadata | None]] = {}
    papers = arxiv_ids_or_urls

    if show_progress:
        papers = tqdm(papers, desc="Converting papers", unit="paper")

    for paper in papers:
        arxiv_id = _extract_arxiv_id(paper)

        if show_progress and isinstance(papers, tqdm):
            papers.set_description(f"Converting {arxiv_id}")

        content, metadata = convert_arxiv_latex(
            paper,
            markdown=markdown,
            redownload_existing=redownload_existing,
            use_cache=use_cache,
            keep_comments=keep_comments,
            include_bibliography=include_bibliography,
            include_metadata=include_metadata,
            working_dir=working_dir,
            pandoc_timeout=pandoc_timeout,
            parse_citations=parse_citations,
        )

        results[arxiv_id] = (content, metadata)

    return results


def main():
    parser = argparse.ArgumentParser(description="Download and convert arXiv papers")
    parser.add_argument("papers", nargs="+", help="arXiv IDs or URLs", type=str)
    parser.add_argument(
        "--output",
        "-o",
        help="Output directory",
        type=Path,
        required=False,
    )
    parser.add_argument(
        "--cache-dir",
        help=f"Directory to use for caching papers (default: {_get_default_cache_dir()})",
        type=Path,
        required=False,
    )
    parser.add_argument(
        "--use-cache",
        help="Use cached files if they exist",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    parser.add_argument(
        "--markdown",
        help="Use pandoc to convert to markdown",
        action=argparse.BooleanOptionalAction,
        required=False,
    )
    parser.add_argument(
        "--redownload-existing",
        help="Redownload existing packages",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    parser.add_argument(
        "--force-overwrite",
        help="Force overwrite of existing files",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    parser.add_argument(
        "--keep-comments",
        help="Keep comments in the expanded LaTeX file",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    parser.add_argument(
        "--bib",
        help="Include bibliography file content",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--metadata",
        help="Include paper metadata (title, authors, etc.)",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--pandoc-timeout",
        help="Maximum execution time for pandoc in seconds (default: 60)",
        type=int,
        default=60,
    )
    parser.add_argument(
        "--verbose",
        help="Enable verbose output",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(level=log_level)

    # Determine markdown format
    if args.markdown is None:
        args.markdown = check_pandoc_installed()

    # Convert the papers
    results = batch_convert_arxiv_papers(
        args.papers,
        markdown=args.markdown,
        redownload_existing=args.redownload_existing,
        use_cache=args.use_cache,
        keep_comments=args.keep_comments,
        include_bibliography=args.bib,
        include_metadata=args.metadata,
        working_dir=args.cache_dir,
        pandoc_timeout=args.pandoc_timeout,
        parse_citations=False,  # Not needed for command line.
    )

    # Handle output based on command-line arguments
    if args.output:
        # Create output directory
        args.output.mkdir(parents=True, exist_ok=True)

        # Write each result to a file
        for arxiv_id, (content, _) in results.items():
            ext = "md" if args.markdown else "tex"
            output_file = args.output / f"{arxiv_id}.{ext}"

            # Check if file exists and handle overwrite
            if output_file.exists() and not args.force_overwrite:
                log.info(
                    f"File {output_file} already exists, skipping (use --force-overwrite to overwrite)"
                )
                continue

            with output_file.open("w", encoding="utf-8") as f:
                f.write(content)  # Write the content part of the tuple
            log.info(f"Wrote {output_file}")
    else:
        # Print to stdout if no output directory specified
        for arxiv_id, (content, _) in results.items():
            print(content)


if __name__ == "__main__":
    main()
