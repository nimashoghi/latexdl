import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from ._texsoup_wrapper import TexSoup


class ExpandError(Exception):
    pass


def expand_latex_file(f_in: Path):
    """Expand a LaTeX file using latexpand utility."""
    expanded_file = f_in.parent / f"expanded_{f_in.name}"

    try:
        result = subprocess.run(
            [
                "latexpand",
                str(f_in.relative_to(f_in.parent)),
                "--output",
                str(expanded_file.relative_to(f_in.parent)),
            ],
            capture_output=True,
            text=True,
            cwd=f_in.parent,
        )

        if result.returncode != 0:
            raise RuntimeError(f"latexpand failed: {result.stderr}")

        return expanded_file.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        raise ExpandError(f"Error expanding {f_in}") from e


def main():
    parser = argparse.ArgumentParser(description="Expand LaTeX files")
    parser.add_argument(
        "--input",
        help="Input LaTeX file. If not provided, the stdin is used.",
        type=Path,
        required=False,
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

    input: Path | None = args.input
    output: Path | None = args.output
    strip_: bool = args.strip

    # Resolve the input file
    if input:
        resolved = expand_latex_file(input)
    else:
        # Create a temporary file for stdin content
        with tempfile.NamedTemporaryFile(
            suffix=".tex", mode="w", encoding="utf-8", delete=False
        ) as tmp:
            tmp.write(sys.stdin.read())
            tmp_path = Path(tmp.name)

        try:
            resolved = expand_latex_file(tmp_path)
        finally:
            tmp_path.unlink()

    if strip_:
        from .strip import strip

        resolved = strip(TexSoup(resolved))

    resolved = str(resolved)

    # Write the output
    if output:
        output.write_text(resolved, encoding="utf-8")
    else:
        print(resolved)


if __name__ == "__main__":
    main()
