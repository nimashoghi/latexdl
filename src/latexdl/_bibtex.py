from __future__ import annotations

import logging
import re
from pathlib import Path

import bibtexparser
import bibtexparser.model

log = logging.getLogger(__name__)

# Expanded citation patterns
CITATION_PATTERNS = [
    r"\\cite(?:a|t|p|author|year|title|alp|num|text)?(?:\*)?(?:\[[^\]]*\])?{(.*?)}",  # Basic and natbib with optional notes
    r"\\(?:parencite|textcite|footcite|autocite|smartcite|supercite)(?:\[[^\]]*\])?{(.*?)}",  # Biblatex
    r"\\(?:cite|parencite|textcite)s(?:\[[^\]]*\])?(?:\[[^\]]*\])?{([^{}]*)}",  # First citation in multiple citations
    r"\\(?:footfullcite|fullcite|citeauthor|citetitle|citeyear){(.*?)}",  # Special formats
]
# Expanded bibliography patterns
BIBLIOGRAPHY_PATTERNS = [
    r"\\bibliography{(.+?)}",  # Standard BibTeX
    r"\\addbibresource{(.+?)}",  # BibLaTeX (might include .bib extension)
    r"\\nobibliography{(.+?)}",  # Custom styles
]


def detect_and_collect_bibtex(
    base_dir: Path,
    expanded_contents: str,
    *,
    remove_unreferenced: bool = True,
    markdown: bool = False,
):
    """
    Given a base directory and expanded LaTeX contents, extract the included
    BibTeX files and return the contents of the merged BibTeX file.

    Args:
        base_dir (Path): The base directory to search for the BibTeX file.
        expanded_contents (str): The expanded LaTeX contents.
        remove_unreferenced (bool): Whether to remove unreferenced BibTeX
            entries from the merged file.
        markdown (bool): Whether to format output in markdown style.

    Returns:
        str | None: The contents of the merged BibTeX file, or None if no
            BibTeX file is included.
    """
    # Find all the included BibTeX files using expanded patterns
    bib_files = []
    for pattern in BIBLIOGRAPHY_PATTERNS:
        for match in re.finditer(pattern, expanded_contents):
            bib_files.extend([f.strip() for f in match.group(1).split(",")])

    # Collect entries from external .bib files
    entries: dict[str, str] = {}
    for bib_file in bib_files:
        # Handle .bib extension if present, otherwise add it
        if not bib_file.endswith(".bib"):
            bib_path = base_dir / f"{bib_file}.bib"
        else:
            bib_path = base_dir / bib_file

        if not bib_path.exists():
            log.warning(f"BibTeX file not found: {bib_path}")
            continue

        # Parse the file and collect the entries
        entries.update(_parse_bibtex_file(bib_path, markdown))

    # Check for manual bibliography environment
    manual_bibs = _extract_manual_bibliography(expanded_contents, markdown)
    if manual_bibs:
        entries.update(manual_bibs)

    # If no entries found, return None
    if not entries:
        log.info("No BibTeX entries found, skipping")
        return None

    # Remove unreferenced keys if requested
    if remove_unreferenced:
        prev_count = len(entries)
        entries = _remove_unreferenced_keys(entries, expanded_contents)
        log.info(
            f"Removed {prev_count - len(entries)}/{prev_count} unreferenced BibTeX entries"
        )

        # If all entries were unreferenced, return None
        if not entries:
            return None

    # Merge the entries into a single BibTeX file
    lines = sorted(entries.items(), key=lambda x: x[0])
    if markdown:
        return "\n".join(content for _, content in lines)
    else:
        return "\n".join(content for _, content in lines)


def _extract_manual_bibliography(
    content: str, markdown: bool = False
) -> dict[str, str]:
    """Extract entries from manual thebibliography environment."""
    entries = {}

    # Find the thebibliography environment
    match = re.search(
        r"\\begin{thebibliography}.*?\\end{thebibliography}", content, re.DOTALL
    )
    if not match:
        return entries

    # Extract bibitem entries
    bib_content = match.group(0)
    for bibitem in re.finditer(
        r"\\bibitem(?:\[.*?\])?{(.*?)}(.*?)(?=\\bibitem|\\end{thebibliography})",
        bib_content,
        re.DOTALL,
    ):
        key = bibitem.group(1)
        text = bibitem.group(2).strip()
        if markdown:
            entries[key] = f"* `[@{key}]` {text}"
        else:
            entries[key] = f"[@{key}] {text}"

    return entries


def _remove_unreferenced_keys(entries: dict[str, str], expanded_contents: str):
    # Use expanded citation patterns to find all referenced keys
    referenced_keys = set()

    for pattern in CITATION_PATTERNS:
        for match in re.finditer(pattern, expanded_contents):
            # Split by comma to handle multiple citations in a single command
            citation_content = match.group(1)
            keys = [key.strip() for key in citation_content.split(",")]
            referenced_keys.update(keys)

    # Keep only the referenced entries
    entries = {k: v for k, v in entries.items() if k in referenced_keys}

    return entries


def _parse_bibtex_file(bib_file: Path, markdown: bool = False):
    try:
        library = bibtexparser.parse_file(str(bib_file.absolute()))
        for entry in library.entries:
            if not (key := entry.key) or not (
                content := _entry_to_text(key, entry, markdown)
            ):
                continue

            yield key, content
    except Exception:
        log.warning(f"Failed to parse BibTeX file {bib_file}", exc_info=True)


def _entry_to_text(
    key: str, entry: bibtexparser.model.Entry, markdown: bool = False
) -> str | None:
    """Format a BibTeX entry in IEEE-like style."""
    if not (title := entry.get("title")):
        return None

    # Format authors (IEEE style: A. Author, B. Author, and C. Author)
    authors = ""
    if author_field := entry.get("author"):
        # Split authors and format them
        author_list = [a.strip() for a in author_field.value.split(" and ")]
        formatted_authors = []

        for author in author_list:
            parts = author.split(",")
            if len(parts) == 2:  # Last, First format
                last, first = parts
                initials = " ".join([f"{n[0]}." for n in first.strip().split()])
                formatted_authors.append(f"{last.strip()}, {initials}")
            else:  # First Last format
                name_parts = author.split()
                if len(name_parts) > 1:
                    last = name_parts[-1]
                    first_initials = " ".join([f"{n[0]}." for n in name_parts[:-1]])
                    formatted_authors.append(f"{last}, {first_initials}")
                else:
                    formatted_authors.append(author)

        if len(formatted_authors) == 1:
            authors = formatted_authors[0]
        elif len(formatted_authors) == 2:
            authors = f"{formatted_authors[0]} and {formatted_authors[1]}"
        else:
            authors = (
                ", ".join(formatted_authors[:-1]) + f", and {formatted_authors[-1]}"
            )

    # Title in quotes
    title_text = f'"{title.value}"'

    # Publication info
    pub_info = ""
    entry_type = entry.entry_type

    if entry_type == "article":
        if journal := entry.get("journal"):
            pub_info += f", {journal.value}"
            if volume := entry.get("volume"):
                pub_info += f", vol. {volume.value}"
                if number := entry.get("number"):
                    pub_info += f", no. {number.value}"
            if pages := entry.get("pages"):
                pub_info += f", pp. {pages.value}"
    elif entry_type == "book":
        if publisher := entry.get("publisher"):
            pub_info += f", {publisher.value}"
    elif entry_type == "inproceedings" or entry_type == "conference":
        if booktitle := entry.get("booktitle"):
            pub_info += f", in {booktitle.value}"

    # Add year
    if year := entry.get("year"):
        pub_info += f", {year.value}"

    # Combine all parts
    citation = f"{authors}, {title_text}{pub_info}."

    # Format according to markdown preference
    if markdown:
        return f"* `[@{key}]` {citation}"
    else:
        return f"[@{key}] {citation}"
