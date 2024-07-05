from typing import Any

from TexSoup import TexSoup as _TexSoup


def TexSoup(contents: str, *args: Any, **kwargs: Any):
    # For some reason, TexSoup struggles with parsing. We fix that here.

    # - $some math here$$some more math here$ (i.e., double dollar signs with no space in between)
    contents = contents.replace("$$", "$ $")

    return _TexSoup(contents, *args, **kwargs)
