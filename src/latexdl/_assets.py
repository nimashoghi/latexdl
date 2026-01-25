from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

log = logging.getLogger(__name__)

# Extensions to try when the original path doesn't have one or file not found
_IMAGE_EXTENSIONS = (".pdf", ".png", ".jpg", ".jpeg", ".eps", ".svg")

# Regex patterns for image references
_MARKDOWN_IMAGE_PATTERN = re.compile(r"!\[.*?\]\(([^)]+)\)")
_HTML_EMBED_PATTERN = re.compile(r'<embed\s+src="([^"]+)"')
_LATEX_INCLUDEGRAPHICS_PATTERN = re.compile(r"\\includegraphics(?:\[.*?\])?\{([^}]+)\}")


def _parse_image_references(content: str, *, markdown: bool) -> list[str]:
    """Extract image paths from content.

    Args:
        content: The converted content (markdown or LaTeX)
        markdown: Whether the content is markdown (True) or LaTeX (False)

    Returns:
        List of image paths found in the content
    """
    if markdown:
        # Parse both markdown image syntax and HTML embed tags
        # (pandoc sometimes outputs <embed src="..."> for figures)
        md_refs = _MARKDOWN_IMAGE_PATTERN.findall(content)
        html_refs = _HTML_EMBED_PATTERN.findall(content)
        return md_refs + html_refs
    else:
        return _LATEX_INCLUDEGRAPHICS_PATTERN.findall(content)


def _resolve_image_path(source_dir: Path, image_ref: str) -> Path | None:
    """Resolve an image reference to an actual file path.

    LaTeX often omits extensions, so we try multiple extensions.

    Args:
        source_dir: Directory containing the source files
        image_ref: Image path from the document

    Returns:
        Path to the actual image file, or None if not found
    """
    # Clean up the reference (remove leading ./ if present)
    image_ref = image_ref.lstrip("./")

    # Try exact path first
    candidate = source_dir / image_ref
    if candidate.exists() and candidate.is_file():
        return candidate

    # If no extension or file not found, try adding extensions
    for ext in _IMAGE_EXTENSIONS:
        candidate = source_dir / f"{image_ref}{ext}"
        if candidate.exists() and candidate.is_file():
            return candidate

    # Try without any transformation as fallback
    log.debug(f"Could not resolve image reference: {image_ref}")
    return None


def copy_assets(
    source_dir: Path,
    output_dir: Path,
    content: str,
    *,
    markdown: bool,
) -> None:
    """Copy referenced image assets from source to output directory.

    Parses the content for image references and copies the referenced files
    to the output directory, preserving the directory structure.

    Args:
        source_dir: Directory containing the arXiv source files
        output_dir: Directory to copy assets to
        content: The converted content (markdown or LaTeX)
        markdown: Whether the content is markdown (True) or LaTeX (False)
    """
    image_refs = _parse_image_references(content, markdown=markdown)
    if not image_refs:
        log.debug("No image references found in content")
        return

    log.info(f"Found {len(image_refs)} image reference(s)")
    copied_count = 0

    for image_ref in image_refs:
        if (source_path := _resolve_image_path(source_dir, image_ref)) is None:
            log.warning(f"Could not find image: {image_ref}")
            continue

        # Compute relative path from source_dir to preserve directory structure
        try:
            rel_path = source_path.relative_to(source_dir)
        except ValueError:
            # File is outside source_dir, just use the filename
            rel_path = Path(source_path.name)

        dest_path = output_dir / rel_path
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        if dest_path.exists():
            log.debug(f"Asset already exists, skipping: {rel_path}")
            continue

        shutil.copy2(source_path, dest_path)
        log.debug(f"Copied: {rel_path}")
        copied_count += 1

    log.info(f"Copied {copied_count} asset(s) to {output_dir}")
