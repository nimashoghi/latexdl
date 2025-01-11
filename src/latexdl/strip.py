import logging

from pylatexenc.latex2text import LatexNodes2Text as _LatexNodes2Text
from typing_extensions import override


class LatexNodes2Text(_LatexNodes2Text):
    @override
    def apply_simplify_repl(self, node, simplify_repl, what):
        try:
            return super().apply_simplify_repl(node, simplify_repl, what)
        except Exception:
            logging.warning(
                f"WARNING: Error in configuration: {what} failed its substitution! "
                "Ignoring the error and continuing."
            )
            return ""


def strip(content: str) -> str:
    return LatexNodes2Text(math_mode="verbatim").latex_to_text(content)
