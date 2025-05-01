from __future__ import annotations

import argparse
import contextlib
import logging
import re
import tarfile
import tempfile
import urllib.parse
from pathlib import Path

import requests
from tqdm import tqdm

from ._bibtex import detect_and_collect_bibtex
from ._metadata import ArxivMetadata, fetch_arxiv_metadata
from .expand import expand_latex_file
from .strip import check_pandoc_installed, strip


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
    output_dir = temp_dir / arxiv_id
    output_dir.mkdir(parents=True, exist_ok=True)

    fpath = temp_dir / f"{arxiv_id}.tar.gz"
    if fpath.exists() and not redownload_existing:
        logging.info(f"Package {arxiv_id} already downloaded, skipping")
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
    keep_comments: bool = False,
    include_bibliography: bool = True,
    include_metadata: bool = True,
    working_dir: str | Path | None = None,
) -> tuple[str, ArxivMetadata | None]:
    """
    Convert an arXiv paper to expanded LaTeX or markdown.

    Args:
        arxiv_id_or_url: arXiv ID or URL of the paper
        markdown: Whether to convert to markdown (requires pandoc)
        redownload_existing: Whether to redownload if archives already exist
        keep_comments: Whether to keep comments in the expanded LaTeX
        include_bibliography: Whether to include bibliography content
        include_metadata: Whether to include paper metadata (title, authors, etc.)
        working_dir: Optional working directory for temporary files

    Returns:
        The expanded LaTeX or converted markdown content as a string, and
        the metadata as an ArxivMetadata object (if `include_metadata` is True).
        If `include_metadata` is False, the metadata will be None.

    Raises:
        RuntimeError: If the main LaTeX file cannot be found
        ValueError: If the arXiv ID format is invalid
    """
    # Extract arXiv ID
    arxiv_id = _extract_arxiv_id(arxiv_id_or_url)

    # Create temporary directory for downloads and extraction
    with contextlib.ExitStack() as stack:
        if working_dir is None:
            temp_dir = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        else:
            temp_dir = Path(working_dir) / arxiv_id
            temp_dir.mkdir(parents=True, exist_ok=True)

        # Download and extract
        src_dir = download_arxiv_source(arxiv_id, temp_dir, redownload_existing)

        # Find main LaTeX file
        main_file = _find_main_latex_file(src_dir)
        if main_file is None:
            raise RuntimeError(f"Could not find main LaTeX file for {arxiv_id}")

        # Expand LaTeX
        expanded_latex = expand_latex_file(main_file, keep_comments=keep_comments)

        # Convert to markdown if requested
        content = strip(expanded_latex) if markdown else expanded_latex

        # Add bibliography if requested
        if include_bibliography:
            bib_content = detect_and_collect_bibtex(
                src_dir, expanded_latex, markdown=markdown
            )
            if bib_content:
                sep = "\n\n# References\n\n" if markdown else "\n\nREFERENCES\n\n"
                content += sep + bib_content

        # Add metadata if requested
        metadata = None
        if include_metadata:
            if (metadata := fetch_arxiv_metadata(arxiv_id)) is not None:
                metadata_content = (
                    metadata.format_for_markdown()
                    if markdown
                    else metadata.format_for_latex()
                )
                content = metadata_content + content
            else:
                logging.warning(f"Could not fetch metadata for {arxiv_id}")

        return content, metadata


def batch_convert_arxiv_papers(
    arxiv_ids_or_urls: list[str],
    *,
    markdown: bool = False,
    redownload_existing: bool = False,
    keep_comments: bool = False,
    include_bibliography: bool = True,
    include_metadata: bool = True,
    show_progress: bool = True,
    working_dir: str | Path | None = None,
) -> dict[str, tuple[str, ArxivMetadata | None]]:
    """
    Convert multiple arXiv papers to expanded LaTeX or markdown.

    Args:
        arxiv_ids_or_urls: List of arXiv IDs or URLs
        markdown: Whether to convert to markdown (requires pandoc)
        redownload_existing: Whether to redownload if archives already exist
        keep_comments: Whether to keep comments in the expanded LaTeX
        include_bibliography: Whether to include bibliography content
        include_metadata: Whether to include paper metadata (title, authors, etc.)
        show_progress: Whether to show a progress bar
        working_dir: Optional working directory for temporary files

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
            keep_comments=keep_comments,
            include_bibliography=include_bibliography,
            include_metadata=include_metadata,
            working_dir=working_dir,
        )

        results[arxiv_id] = (content, metadata)

    return results


def main():
    logging.basicConfig(level=logging.INFO)

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
    args = parser.parse_args()

    # Determine markdown format
    if args.markdown is None:
        args.markdown = check_pandoc_installed()

    # Convert the papers
    results = batch_convert_arxiv_papers(
        args.papers,
        markdown=args.markdown,
        redownload_existing=args.redownload_existing,
        keep_comments=args.keep_comments,
        include_bibliography=args.bib,
        include_metadata=args.metadata,
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
                logging.info(
                    f"File {output_file} already exists, skipping (use --force-overwrite to overwrite)"
                )
                continue

            with output_file.open("w", encoding="utf-8") as f:
                f.write(content)  # Write the content part of the tuple
            logging.info(f"Wrote {output_file}")
    else:
        # Print to stdout if no output directory specified
        for arxiv_id, (content, _) in results.items():
            print(content)


if __name__ == "__main__":
    main()
