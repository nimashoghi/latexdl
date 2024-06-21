import argparse
from pathlib import Path
from typing import Any, cast

from TexSoup import TexNode, TexSoup


def expand_latex_file(f: Path, *, root: Path, imported: set[Path]):
    """Resolve all imports and update the parse tree.

    Reads from a tex file and once finished, writes to a tex file.
    """
    # If we've already imported this file, return an empty node
    if f.absolute() in imported:
        return TexSoup("")

    # Otherwise, add this file to the set of imported files
    imported.add(f.absolute())

    # Read the file and resolve imports.
    soup = TexSoup(f.read_text(encoding="utf-8"))

    # Resolve input and include commands (e.g., \input{file.tex})
    # (as far as we're concerned, they're the same).
    for command in ("input", "include"):
        for node in soup.find_all(command):
            if not isinstance(node, TexNode) or len(node.args) != 1:
                continue

            arg = cast(Any, node.args[0]).string
            if not isinstance(arg, str):
                continue

            node.replace_with(
                expand_latex_file(f.parent / arg, root=root, imported=imported).expr
            )

    # Resolve imports, e.g., \import{dir/}{file.tex}
    for import_ in soup.find_all("import"):
        if not isinstance(import_, TexNode) or len(import_.args) != 2:
            continue

        arg1 = cast(Any, import_.args[0]).string
        arg2 = cast(Any, import_.args[1]).string
        if not isinstance(arg1, str) or not isinstance(arg2, str):
            continue

        import_.replace_with(
            expand_latex_file(root / (arg1 + arg2), root=root, imported=imported).expr
        )

    # Resolve subimports, e.g., \subimport{dir/}{file.tex}
    # This works similarly to \import, but the path is relative to the current file
    for subimport in soup.find_all("subimport"):
        if not isinstance(subimport, TexNode) or len(subimport.args) != 2:
            continue

        arg1 = cast(Any, subimport.args[0]).string
        arg2 = cast(Any, subimport.args[1]).string
        if not isinstance(arg1, str) or not isinstance(arg2, str):
            continue

        subimport.replace_with(
            expand_latex_file(
                f.parent / (arg1 + arg2), root=root, imported=imported
            ).expr
        )

    return soup


def latexpand(f: Path, root: Path | None = None):
    if root is None:
        root = f.parent
    return str(expand_latex_file(f, root=root, imported=set()))


def main():
    parser = argparse.ArgumentParser(description="Expand LaTeX files")
    parser.add_argument("input", help="Input LaTeX file", type=Path)
    parser.add_argument(
        "--output",
        help="Output LaTeX file. If not provided, the output is printed to stdout.",
        type=Path,
        required=False,
    )
    args = parser.parse_args()

    # Resolve the input file
    resolved = latexpand(args.input)

    # Write the output
    if args.output:
        args.output.write_text(resolved, encoding="utf-8")
    else:
        print(resolved)


if __name__ == "__main__":
    main()
