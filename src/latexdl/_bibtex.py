from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import bibtexparser
import bibtexparser.model

from ._types import ParsedCitation

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CollectBibtexOutput:
    references_str: str
    """Contents of the merged BibTeX file."""

    citations: list[ParsedCitation] | None = None
    """Parsed citations from the BibTeX file, if `parse_citations` is True.
    Else None."""

    def __bool__(self):
        """Check if the object is not empty."""
        return bool(self.references_str)


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
    main_tex_path: Path | None = None,
    remove_unreferenced: bool = True,
    markdown: bool = False,
    parse_citations: bool = True,
) -> CollectBibtexOutput | None:
    """
    Given a base directory and expanded LaTeX contents, extract the included
    BibTeX files and return the contents of the merged BibTeX file.

    Args:
        base_dir (Path): The base directory to search for the BibTeX file.
        expanded_contents (str): The expanded LaTeX contents.
        main_tex_path (Path | None): Path to the main LaTeX file, used to look for a .bbl file
            with the same basename if no .bib files are found.
        remove_unreferenced (bool): Whether to remove unreferenced BibTeX
            entries from the merged file.
        markdown (bool): Whether to format output in markdown style.
        parse_citations (bool): Whether to parse citations from the BibTeX
            entries.

    Returns:
        CollectBibtexOutput | None: The output containing the merged BibTeX file
            contents and parsed citations.
    """
    # Find all the included BibTeX files using expanded patterns
    bib_files = []
    for pattern in BIBLIOGRAPHY_PATTERNS:
        for match in re.finditer(pattern, expanded_contents):
            bib_files.extend([f.strip() for f in match.group(1).split(",")])

    # Collect entries from external .bib files
    entries: dict[str, tuple[str, ParsedCitation | None]] = {}
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
        entries.update(
            _parse_bibtex_file(
                bib_path,
                markdown,
                parse_citations=parse_citations,
            )
        )

    # Check for manual bibliography environment
    if manual_bibs := _extract_manual_bibliography(
        expanded_contents,
        markdown,
        parse_citations=parse_citations,
    ):
        entries.update(manual_bibs)

    # If no entries found in .bib files or thebibliography environment,
    # try to find a .bbl file with the same basename as the main tex file
    if (
        not entries
        and main_tex_path is not None
        and (bbl_path := main_tex_path.with_suffix(".bbl")).exists()
    ):
        log.info(f"No .bib files found, using .bbl file: {bbl_path}")
        try:
            with bbl_path.open("r", encoding="utf-8") as f:
                bbl_content = f.read()

            # Extract bibliography entries from the .bbl file
            bbl_entries = _extract_bbl_bibliography(
                bbl_content,
                markdown,
                parse_citations=parse_citations,
            )
            if bbl_entries:
                entries.update(bbl_entries)
                log.info(f"Extracted {len(bbl_entries)} entries from .bbl file")
        except Exception as e:
            log.warning(f"Error reading .bbl file {bbl_path}: {e}")

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
    references_str = "\n".join(content for _, (content, _) in lines)
    citations = [parsed for _, (_, parsed) in lines if parsed]
    return CollectBibtexOutput(references_str=references_str, citations=citations)


def _manual_bibliography_to_parsed_citation(cleaned_text: str, key: str):
    citation: ParsedCitation | None = None

    try:
        # Most bibliography entries follow the pattern: "Author(s). Title. Journal/Publisher info"
        # or "Author(s), Title, Journal/Publisher info"

        # First, try to extract authors
        authors = []
        author_pattern = r"^([^\.,:]+)(?:\.|\,)"
        author_match = re.match(author_pattern, cleaned_text)
        if author_match:
            author_text = author_match.group(1).strip()
            # Check if there are multiple authors (typically separated by 'and' or commas)
            if " and " in author_text:
                authors = [a.strip() for a in author_text.split(" and ")]
            else:
                # If no 'and', assume a single author or author list with commas
                authors = [author_text]

        # Try to extract title - this is more challenging without specific metadata
        # We'll use a heuristic: the first quoted text or the text between the author and the next period
        title = ""
        title_pattern1 = r"[\"\"]([^\"\"]+)[\"\"]"  # Quoted title
        title_pattern2 = (
            r"(?:\.|\,)\s*([^\.]+)\."  # Text after author until next period
        )

        title_match = re.search(title_pattern1, cleaned_text)
        if title_match:
            title = title_match.group(1).strip()
        else:
            title_match = re.search(title_pattern2, cleaned_text)
            if title_match:
                title = title_match.group(1).strip()

        citation = ParsedCitation(id=key, title=title, authors=authors)
    except Exception:
        log.warning(
            f"Failed to create ParsedCitation for manual bibliography entry {key}",
            exc_info=True,
        )

    return citation


def _extract_manual_bibliography(
    content: str,
    markdown: bool = False,
    parse_citations: bool = True,
):
    """Extract entries from manual thebibliography environment and clean formatting."""
    entries: dict[str, tuple[str, ParsedCitation | None]] = {}

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
        raw_text = bibitem.group(2).strip()

        # Clean the text by removing LaTeX formatting
        cleaned_text = _clean_latex_formatting(raw_text)

        if markdown:
            text = f"* `[@{key}]` {cleaned_text}"
        else:
            text = f"[@{key}] {cleaned_text}"

        parsed = (
            _manual_bibliography_to_parsed_citation(cleaned_text, key)
            if parse_citations
            else None
        )
        entries[key] = (text, parsed)

    return entries


def _bbl_to_parsed_citation(cleaned_text: str, key: str):
    citation: ParsedCitation | None = None
    try:
        # Most BBL entries follow the pattern: "Author(s). Title. Journal/Publisher info"
        # or "Author(s), Title, Journal/Publisher info"

        # First, try to extract authors
        authors = []
        author_pattern = r"^([^\.,:]+)(?:\.|\,)"
        author_match = re.match(author_pattern, cleaned_text)
        if author_match:
            author_text = author_match.group(1).strip()
            # Check if there are multiple authors (typically separated by 'and' or commas)
            if " and " in author_text:
                authors = [a.strip() for a in author_text.split(" and ")]
            else:
                # If no 'and', assume a single author or author list with commas
                authors = [author_text]

        # Try to extract title - this is more challenging without specific metadata
        # We'll use a heuristic: the first quoted text or the text between the author and the next period
        title = ""
        title_pattern1 = r"[\"\"]([^\"\"]+)[\"\"]"  # Quoted title
        title_pattern2 = (
            r"(?:\.|\,)\s*([^\.]+)\."  # Text after author until next period
        )

        title_match = re.search(title_pattern1, cleaned_text)
        if title_match:
            title = title_match.group(1).strip()
        else:
            title_match = re.search(title_pattern2, cleaned_text)
            if title_match:
                title = title_match.group(1).strip()

        citation = ParsedCitation(id=key, title=title, authors=authors)
    except Exception:
        log.warning(
            f"Failed to create ParsedCitation for BBL entry {key}", exc_info=True
        )

    return citation


def _extract_bbl_bibliography(
    bbl_content: str,
    markdown: bool = False,
    parse_citations: bool = True,
):
    """Extract entries from a .bbl file and strip LaTeX formatting."""
    entries: dict[str, tuple[str, ParsedCitation | None]] = {}

    # Check if the .bbl file contains a thebibliography environment
    if not (
        match := re.search(
            r"\\begin{thebibliography}.*?\\end{thebibliography}", bbl_content, re.DOTALL
        )
    ):
        return entries

    # Extract bibitem entries from the bbl file
    bib_content = match.group(0)
    for bibitem in re.finditer(
        r"\\bibitem(?:\[.*?\])?{(.*?)}(.*?)(?=\\bibitem|\\end{thebibliography})",
        bib_content,
        re.DOTALL,
    ):
        key = bibitem.group(1)
        raw_text = bibitem.group(2).strip()

        # Clean the text by removing LaTeX formatting
        cleaned_text = _clean_latex_formatting(raw_text)

        if markdown:
            text = f"* `[@{key}]` {cleaned_text}"
        else:
            text = f"[@{key}] {cleaned_text}"

        parsed = _bbl_to_parsed_citation(cleaned_text, key) if parse_citations else None
        entries[key] = (text, parsed)

    return entries


def _clean_latex_formatting(text: str) -> str:
    """Remove LaTeX formatting commands and consolidate text to a single line.

    Args:
        text: Text containing LaTeX formatting commands

    Returns:
        Cleaned text with LaTeX formatting removed and on a single line
    """
    # Replace common LaTeX commands
    replacements = [
        # Replace newblock with space
        (r"\\newblock\s*", " "),
        # Replace emph and textit with plain text
        (r"\\emph{(.*?)}", r"\1"),
        (r"\\textit{(.*?)}", r"\1"),
        (r"\\textbf{(.*?)}", r"\1"),
        # Remove formatting for special characters like tilde, etc.
        (r"~", " "),
        (r"``|''|\"|``|''", '"'),
        # Clean up special brackets and braces
        (r"{\\\"(.)}", r"\1"),
        (r"{\\\'(.)}", r"\1"),
        (r"{\\`(.)}", r"\1"),
        (r"{\\^(.)}", r"\1"),
        (r"{\\~(.)}", r"\1"),
        (r"{\\c(.)}", r"\1"),
        (r"{\\v(.)}", r"\1"),
        (r"{\\=(.)}", r"\1"),
        (r"{\\.(.)}", r"\1"),
        (r"{\\u(.)}", r"\1"),
        (r"{\\H(.)}", r"\1"),
        # Fix special characters and accents
        (r"{\\\"{a}}", "ä"),
        (r"{\\\"{e}}", "ë"),
        (r"{\\\"{i}}", "ï"),
        (r"{\\\"{o}}", "ö"),
        (r"{\\\"{u}}", "ü"),
        (r"{\\\'e}", "é"),
        (r"{\\\'a}", "á"),
        (r"{\\\'i}", "í"),
        (r"{\\\'o}", "ó"),
        (r"{\\\'u}}", "ú"),
        (r"{\\`e}", "è"),
        (r"{\\`a}", "à"),
        (r"{\\`i}", "ì"),
        (r"{\\`o}", "ò"),
        (r"{\\`u}", "ù"),
        # Handle specific LaTeX symbols/commands
        (r"\\&", "&"),
        (r"\\%", "%"),
        (r"\\_", "_"),
        (r"\\#", "#"),
        (r"\\textdollar", "$"),
        # Remove inline math
        (r"\$(.+?)\$", r"\1"),
        # Clean up any remaining LaTeX commands with arguments
        (r"\\[a-zA-Z]+{(.*?)}", r"\1"),
        # Remove remaining LaTeX commands without arguments
        (r"\\[a-zA-Z]+", " "),
        # Clean up unnecessary curly braces
        (r"{([^{}]*)}", r"\1"),
        # Fix spacing around punctuation
        (r"\s+([.,;:!?])", r"\1"),
        # Normalize whitespace
        (r"\s+", " "),
    ]

    result = text
    for pattern, replacement in replacements:
        result = re.sub(pattern, replacement, result)

    # Collapse multiple spaces and remove leading/trailing whitespace
    result = re.sub(r"\s+", " ", result).strip()

    # Remove any remaining curly braces (this might need multiple passes)
    for _ in range(3):
        result = re.sub(r"{([^{}]*)}", r"\1", result)

    return result


def _remove_unreferenced_keys(
    entries: Mapping[str, tuple[str, ParsedCitation | None]],
    expanded_contents: str,
):
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


def _bibtex_to_parsed_citation(entry: bibtexparser.model.Entry, key: str):
    # Create a ParsedCitation object
    citation: ParsedCitation | None = None
    try:
        title = title.value if (title := entry.get("title")) else ""

        # Extract authors
        authors = []
        if author_field := entry.get("author"):
            author_list = [a.strip() for a in author_field.value.split(" and ")]
            for author in author_list:
                # Simplified author formatting for the list
                parts = author.split(",")
                if len(parts) == 2:  # Last, First format
                    last, first = parts
                    authors.append(f"{first.strip()} {last.strip()}")
                else:  # First Last format
                    authors.append(author)

        citation = ParsedCitation(id=key, title=title, authors=authors)
    except Exception:
        log.warning(f"Failed to create ParsedCitation for {key}", exc_info=True)

    return citation


def _parse_bibtex_file(
    bib_file: Path, markdown: bool = False, parse_citations: bool = True
):
    try:
        library = bibtexparser.parse_file(str(bib_file.absolute()))
        for entry in library.entries:
            if not (key := entry.key) or not (
                content := _entry_to_text(key, entry, markdown)
            ):
                continue

            citation = (
                _bibtex_to_parsed_citation(entry, key) if parse_citations else None
            )
            yield key, (content, citation)
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
