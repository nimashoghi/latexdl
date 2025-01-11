def strip(content: str) -> str:
    from pylatexenc.latex2text import LatexNodes2Text

    return LatexNodes2Text(
        keep_braced_groups=True,
        # keep_inline_math=True,
        math_mode="with-delimiters",
    ).latex_to_text(content)
