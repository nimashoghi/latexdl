from __future__ import annotations

from pathlib import Path

from ._commands import CommandError, run_command


class ExpandError(Exception):
    pass


def expand_latex_file(
    f_in: Path,
    output_path: Path,
    *,
    keep_comments: bool,
    timeout_seconds: int,
) -> str:
    """Expand a LaTeX project without writing into the canonical source tree."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    args = [
        "latexpand",
        f_in.name,
        "--output",
        str(output_path),
    ]
    if keep_comments:
        args.extend(["--keep-comments", "--empty-comments"])

    try:
        run_command(
            args,
            cwd=f_in.parent,
            timeout_seconds=timeout_seconds,
        )
        return output_path.read_text(encoding="utf-8", errors="replace")
    except (CommandError, OSError) as error:
        raise ExpandError(f"error expanding {f_in}: {error}") from error
