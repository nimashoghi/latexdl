from pathlib import Path

from .expand import expand_latex_file
from .strip import strip


def convert_latex_to_latex(
    main_file: Path,
    *,
    strip_comments: bool = True,
    strip_whitespace: bool = True,
    strip_clutter: bool = True,
    seek_to_document: bool = True,
) -> str:
    """
    Process LaTeX using the TexSoup-based method.

    Args:
        main_file: Path to main LaTeX file
        strip_comments: Whether to strip comments
        strip_whitespace: Whether to strip whitespace
        strip_clutter: Whether to strip clutter
        seek_to_document: Whether to seek to document node

    Returns:
        str: Processed LaTeX content
    """
    # Expand the LaTeX file (i.e., resolve imports into 1 large file)
    latex_root = expand_latex_file(main_file, root=main_file.parent, imported=set())

    # Strip comments and whitespace
    latex_root = strip(
        latex_root,
        strip_comments=strip_comments,
        strip_whitespace=strip_whitespace,
        strip_clutter=strip_clutter,
        seek_to_document_node=seek_to_document,
    )

    return str(latex_root)
