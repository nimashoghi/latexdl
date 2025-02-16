import logging
import re
from pathlib import Path

import ahocorasick
import bibtexparser
import bibtexparser.model

log = logging.getLogger(__name__)


def detect_and_collect_bibtex(
    base_dir: Path,
    expanded_contents: str,
    *,
    remove_unreferenced: bool = True,
):
    """
    Given a base directory and expanded LaTeX contents, extract the included
    BibTeX files and return the contents of the merged BibTeX file, in a
    format suitable for LLMs.

    Args:
        base_dir (Path): The base directory to search for the BibTeX file.
        expanded_contents (str): The expanded LaTeX contents.
        remove_unreferenced (bool): Whether to remove unreferenced BibTeX
            entries from the merged file.

    Returns:
        str | None: The contents of the merged BibTeX file, or None if no
            BibTeX file is included.
    """

    # Find all the included BibTeX files by searching for \bibliography{[path to file]}
    if not (bib_files := re.findall(r"\\bibliography{(.+?)}", expanded_contents)):
        return None

    # Collect the contents of the BibTeX files
    entries: dict[str, str] = {}
    for bib_file in bib_files:
        if not (bib_file_path := base_dir / f"{bib_file}.bib").exists():
            continue

        # Parse the file and collect the entries
        entries.update(_parse_bibtex_file(bib_file_path))

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

    # Merge the entries into a single BibTeX file
    lines = sorted(entries.items(), key=lambda x: x[0])
    return "\n".join(content for _, content in lines)


def _remove_unreferenced_keys(entries: dict[str, str], expanded_contents: str):
    # Remove keys that are not referenced in the LaTeX content using Aho-Corasick
    automaton = ahocorasick.Automaton()
    for key in entries.keys():
        # We look for \cite{key} or similar patterns
        cite_patterns = [f"\\cite{{{key}}}", f"\\citep{{{key}}}", f"\\citet{{{key}}}"]
        for pattern in cite_patterns:
            automaton.add_word(pattern, key)

    automaton.make_automaton()

    # Find all referenced keys
    referenced_keys = set()
    for _, key in automaton.iter(expanded_contents):
        referenced_keys.add(key)

    # Keep only the referenced entries if requested
    entries = {k: v for k, v in entries.items() if k in referenced_keys}

    return entries


def _parse_bibtex_file(bib_file: Path):
    try:
        library = bibtexparser.parse_file(str(bib_file.absolute()))
        for entry in library.entries:
            if not (key := entry.key) or not (content := _entry_to_text(key, entry)):
                continue

            yield key, content
    except Exception:
        log.warning(f"Failed to parse BibTeX file {bib_file}", exc_info=True)


def _entry_to_text(key: str, entry: bibtexparser.model.Entry) -> str | None:
    if not (title := entry.get("title")):
        return None

    contents: str = f'"{title.value}"'
    if year := entry.get("year"):
        contents += f" ({year.value})"

    return f"- {key}: {contents}"
