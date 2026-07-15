from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pypandoc


class CommandError(RuntimeError):
    """Raised when an external conversion tool fails."""


def pandoc_path() -> str:
    """Return the bundled Pandoc executable path."""
    return pypandoc.get_pandoc_path()


def run_command(
    command: list[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a killable subprocess and raise a detailed error on failure."""
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            input=input_text,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise CommandError(
            f"command timed out after {timeout_seconds}s: {' '.join(command)}"
        ) from error
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "no output"
        raise CommandError(
            f"command failed with exit code {result.returncode}: "
            f"{' '.join(command)}\n{detail[-4000:]}"
        )
    return result


def run_sandboxed(
    command: list[str],
    *,
    cwd: Path,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    """Run an untrusted document renderer in an offline bubblewrap sandbox."""
    if shutil.which("bwrap") is None:
        raise CommandError("bubblewrap is required for document rendering")

    sandbox = [
        "bwrap",
        "--die-with-parent",
        "--new-session",
        "--unshare-net",
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--tmpfs",
        "/tmp",
    ]
    for system_path in ("/usr", "/bin", "/lib", "/lib64", "/etc", "/var"):
        if Path(system_path).exists():
            sandbox.extend(["--ro-bind", system_path, system_path])
    sandbox.extend(
        [
            "--bind",
            str(cwd),
            "/work",
            "--chdir",
            "/work",
            "--setenv",
            "HOME",
            "/tmp",
            "--setenv",
            "TEXMFVAR",
            "/tmp/texmf-var",
            "--setenv",
            "TEXMFCONFIG",
            "/tmp/texmf-config",
            "--",
            *command,
        ]
    )
    return run_command(sandbox, cwd=cwd, timeout_seconds=timeout_seconds)


def collect_tool_versions() -> dict[str, str]:
    """Collect stable version strings for every tool that affects output."""
    commands = {
        "pandoc": [pandoc_path(), "--version"],
        "latexpand": ["latexpand", "--version"],
        "pdflatex": ["pdflatex", "--version"],
        "pdfcrop": ["pdfcrop", "--version"],
        "pdftocairo": ["pdftocairo", "-v"],
        "ghostscript": ["gs", "--version"],
        "bubblewrap": ["bwrap", "--version"],
    }
    versions: dict[str, str] = {}
    for name, command in commands.items():
        executable = command[0]
        if Path(executable).is_absolute():
            available = Path(executable).is_file()
        else:
            available = shutil.which(executable) is not None
        if not available:
            versions[name] = "missing"
            continue
        try:
            result = subprocess.run(
                command,
                text=True,
                capture_output=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            versions[name] = f"unavailable: {error}"
            continue
        output = result.stdout.strip() or result.stderr.strip()
        versions[name] = output.splitlines()[0] if output else "unknown"
    return versions
