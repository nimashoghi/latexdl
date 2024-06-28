import argparse
import fileinput
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from TexSoup import TexNode, TexSoup


def _resolve_file(f: Path):
    if f.exists():
        # If the file is not a tex file, return None
        if f.suffix != ".tex":
            return None

        return f

    # If the file doesn't exist, try adding the .tex extension
    f = f.with_suffix(".tex")
    if f.exists():
        return f

    return None


def _file_to_args(f: Path) -> tuple[Callable[[], str], str, Path]:
    return lambda: f.read_text(encoding="utf-8"), str(f.absolute()), f.parent


def expand_latex_file(
    contents: Callable[[], str],
    key: str,
    f_dir: Path,
    *,
    root: Path,
    imported: set[str],
):
    """Resolve all imports and update the parse tree.

    Reads from a tex file and once finished, writes to a tex file.
    """
    # If we've already imported this file, return an empty node
    if key in imported:
        return TexSoup("")

    # Otherwise, add this file to the set of imported files
    imported.add(key)

    # Read the file and resolve imports.
    soup = TexSoup(contents())

    # Resolve input and include commands (e.g., \input{file.tex})
    # (as far as we're concerned, they're the same).
    for command in ("input", "include"):
        for node in soup.find_all(command):
            if not isinstance(node, TexNode) or len(node.args) != 1:
                continue

            arg = cast(Any, node.args[0]).string
            if not isinstance(arg, str):
                continue

            # node.replace_with(
            #     expand_latex_file(f_dir / arg, root=root, imported=imported).expr
            # )

            if (new_file := _resolve_file(f_dir / arg)) is None:
                continue
            node.replace_with(
                expand_latex_file(
                    *_file_to_args(new_file), root=root, imported=imported
                ).expr
            )

    # Resolve imports, e.g., \import{dir/}{file.tex}
    for import_ in soup.find_all("import"):
        if not isinstance(import_, TexNode) or len(import_.args) != 2:
            continue

        arg1 = cast(Any, import_.args[0]).string
        arg2 = cast(Any, import_.args[1]).string
        if not isinstance(arg1, str) or not isinstance(arg2, str):
            continue

        # import_.replace_with(
        #     expand_latex_file(root / (arg1 + arg2), root=root, imported=imported).expr
        # )

        if (new_file := _resolve_file(root / arg1 / arg2)) is None:
            continue

        import_.replace_with(
            expand_latex_file(
                *_file_to_args(new_file), root=root, imported=imported
            ).expr
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

        # subimport.replace_with(
        #     expand_latex_file(
        #         f_dir / (arg1 + arg2), root=root, imported=imported
        #     ).expr
        # )

        if (new_file := _resolve_file(f_dir / arg1 / arg2)) is None:
            continue

        subimport.replace_with(
            expand_latex_file(
                *_file_to_args(new_file), root=root, imported=imported
            ).expr
        )

    return soup


def main():
    parser = argparse.ArgumentParser(description="Expand LaTeX files")
    parser.add_argument(
        "input",
        help="Input LaTeX file. If not provided, the stdin is used.",
        type=Path,
        nargs="?",
    )
    parser.add_argument(
        "--strip",
        help="Strip comments, whitespace, and clutter",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    parser.add_argument(
        "--output",
        help="Output LaTeX file. If not provided, the output is printed to stdout.",
        type=Path,
        required=False,
    )
    args = parser.parse_args()

    # Resolve the input file
    if args.input:
        resolved = expand_latex_file(
            *_file_to_args(args.input),
            root=args.input.parent,
            imported=set(),
        )
    else:
        resolved = expand_latex_file(
            lambda: "".join(fileinput.input()),
            "<stdin>",
            Path.cwd(),
            root=Path.cwd(),
            imported=set(),
        )

    if args.strip:
        from .strip import strip

        resolved = strip(resolved)

    resolved = str(resolved)

    # Write the output
    if args.output:
        args.output.write_text(resolved, encoding="utf-8")
    else:
        print(resolved)


if __name__ == "__main__":
    main()
