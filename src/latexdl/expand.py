import subprocess
from pathlib import Path


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
