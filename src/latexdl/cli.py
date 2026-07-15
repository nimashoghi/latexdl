from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from ._commands import collect_tool_versions
from .converter import convert_arxiv
from .models import ConversionRequest

_REQUIRED_TOOLS = (
    "pandoc",
    "latexpand",
    "pdflatex",
    "pdfcrop",
    "pdftocairo",
    "ghostscript",
    "bubblewrap",
)


def main(argv: list[str] | None = None) -> int:
    """Run the latexdl command-line interface."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING)
    if args.command == "doctor":
        return _doctor(as_json=args.json)
    if args.command == "convert":
        result = convert_arxiv(
            ConversionRequest(
                paper=args.paper,
                output_dir=args.output_dir,
                cache_dir=args.cache_dir,
                use_cache=args.cache,
                force=args.force,
                include_metadata=args.metadata,
                include_bibliography=args.bibliography,
                keep_comments=args.keep_comments,
                preserve_macros=args.preserve_macros,
                timeout_seconds=args.timeout,
                render_dpi=args.render_dpi,
            )
        )
        print(result.paper_path)
        if not result.report.complete:
            print(
                f"conversion is partial; inspect {result.report_path}",
                file=sys.stderr,
            )
            return 2
        return 0
    parser.error("a command is required")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="latexdl",
        description="Convert arXiv LaTeX sources into complete Markdown bundles.",
    )
    parser.add_argument("--verbose", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)

    convert = subparsers.add_parser("convert", help="convert one arXiv paper")
    convert.add_argument("paper", help="arXiv ID or canonical URL")
    convert.add_argument("output_dir", type=Path, help="exact bundle output directory")
    convert.add_argument("--cache-dir", type=Path)
    convert.add_argument("--cache", action=argparse.BooleanOptionalAction, default=True)
    convert.add_argument("--force", action="store_true")
    convert.add_argument(
        "--metadata", action=argparse.BooleanOptionalAction, default=True
    )
    convert.add_argument(
        "--bibliography", action=argparse.BooleanOptionalAction, default=True
    )
    convert.add_argument("--keep-comments", action="store_true")
    convert.add_argument("--preserve-macros", action="store_true")
    convert.add_argument("--timeout", type=int, default=120)
    convert.add_argument("--render-dpi", type=int, default=180)

    doctor = subparsers.add_parser("doctor", help="check conversion dependencies")
    doctor.add_argument("--json", action="store_true")
    return parser


def _doctor(*, as_json: bool) -> int:
    versions = collect_tool_versions()
    missing = [name for name in _REQUIRED_TOOLS if versions.get(name) == "missing"]
    if as_json:
        print(json.dumps({"tools": versions, "missing": missing}, indent=2))
    else:
        for name, version in versions.items():
            print(f"{name}: {version}")
        if missing:
            print(f"missing required tools: {', '.join(missing)}", file=sys.stderr)
    return 1 if missing else 0
