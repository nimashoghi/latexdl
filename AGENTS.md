# AGENTS.md

This file provides guidance to AI agents when working with code in this repository.

## Project Overview

latexdl is a Python utility that downloads arXiv papers and processes their LaTeX source into expanded LaTeX or Markdown. It handles flattening multi-file LaTeX projects, extracting structured metadata, and collecting bibliographies.

## Development Commands

```bash
# Install for development
uv sync --all-extras --all-groups

# Run tests
uv run pytest

# Run a single test file
uv run pytest tests/bibtext/test_bibtex.py

# Run a specific test
uv run pytest tests/bibtext/test_bibtex.py::test_function_name -v

# Type checking
uv run basedpyright

# Linting and formatting
uv run ruff check src/
uv run ruff format src/
```

## External Dependencies

Run `uv run latexdl doctor` for the authoritative check. Conversion requires
`latexpand`, `pdflatex`, `pdfcrop`, `pdftocairo`, Ghostscript, and Bubblewrap.
Pandoc is bundled through `pypandoc-binary`.

## CLI Entry Points

- `latexdl`: Main CLI for downloading and converting papers
- `latexdl-mcp`: MCP server for AI tool integration

## Architecture

**Core processing flow** (in `converter.py`):

1. Download a versioned arXiv source archive atomically and extract it safely.
2. Build from a disposable source copy and expand LaTeX with `latexpand`.
3. Parse Pandoc JSON, recover empty/dropped figures and tables, then write GFM.
4. Resolve and rewrite every media target; render vector assets to PNG while
   preserving originals.
5. Validate completeness, write structured/human reports, and atomically install
   the portable bundle.

**Key modules**:

- `converter.py`: conversion orchestration and atomic bundle/cache handling
- `models.py`: public request, result, report, asset, and diagnostic models
- `cli.py`: `convert` and `doctor` commands
- `_source.py`: arXiv ID parsing, atomic downloads, and safe archive extraction
- `_pandoc.py`: Pandoc JSON conversion and figure/table recovery
- `_commands.py`: killable subprocesses, sandboxing, and tool discovery
- `mcp.py`: FastMCP server exposing `read_paper` and `get_paper_structure` tools
- `_assets.py`: media resolution, conversion, preview rendering, and validation
- `_types.py`: arXiv metadata and citation types

**Public API** (exported from `__init__.py`):

- `convert_arxiv(ConversionRequest) -> ConversionResult`
- `convert_many(Sequence[ConversionRequest]) -> list[ConversionResult]`
- `ConversionRequest`, `ConversionResult`, `ConversionReport`, `AssetRecord`, and
  `Diagnostic`

Version 3 is intentionally breaking. Do not reintroduce the tuple- or
`Path`-returning version 2 APIs as compatibility wrappers.

## Code Style

- All files must have `from __future__ import annotations` (enforced by ruff)
- Type checking via basedpyright in "standard" mode
- Python >=3.10
