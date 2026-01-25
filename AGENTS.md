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

- **latexpand**: System tool for LaTeX expansion (install via TeX Live)
- **pandoc**: For Markdown conversion (bundled via `pypandoc-binary`)

## CLI Entry Points

- `latexdl`: Main CLI for downloading and converting papers
- `latexdl-mcp`: MCP server for AI tool integration

## Architecture

**Core processing flow** (in `main.py`):

1. Download arXiv source → Extract tarball → Find main .tex file
2. Expand LaTeX via `latexpand` (`expand.py`)
3. Convert to Markdown via `pandoc` (`strip.py`) if requested
4. Collect BibTeX references (`_bibtex.py`)
5. Attach arXiv metadata (`_metadata.py`)
6. Copy referenced image assets to output directory (`_assets.py`)

**Key modules**:

- `main.py`: CLI and orchestration logic; `convert_arxiv_latex()` is the main API function
- `mcp.py`: FastMCP server exposing `read_paper` and `get_paper_structure` tools
- `_cache.py`: Pydantic-based caching in platform-specific user cache directory
- `_assets.py`: Asset copying (parses image references and copies files to output)
- `_types.py`: Type definitions including `ArxivMetadata` and `ConversionResult`

**Public API** (exported from `__init__.py`):

- `convert_arxiv_latex()`: Convert single paper (returns content + metadata)
- `convert_arxiv_to_directory()`: Convert paper and write to directory with assets
- `batch_convert_arxiv_papers()`: Convert multiple papers
- `robust_download_paper()`: Download with fallback behavior
- `download_arxiv_source()`: Just download and extract source
- `ConversionResult`: Dataclass with content, metadata, and source_dir

## Code Style

- All files must have `from __future__ import annotations` (enforced by ruff)
- Type checking via basedpyright in "standard" mode
- Python >=3.10
