# latexdl

`latexdl` converts an arXiv LaTeX source package into a portable Markdown
bundle. It treats figures, tables, provenance, and conversion diagnostics as
part of the result rather than best-effort side effects.

## Install

Python 3.10 or newer and these system tools are required:

- `latexpand`
- a TeX installation providing `pdflatex` and `pdfcrop`
- Poppler's `pdftocairo`
- Ghostscript (`gs`)
- Bubblewrap (`bwrap`)

Pandoc is supplied by `pypandoc-binary`.

```bash
uv sync --all-extras --all-groups
uv run latexdl doctor
```

## Command line

```bash
uv run latexdl convert 2505.11831 ./arc-agi-2
uv run latexdl convert https://arxiv.org/abs/2603.24621 ./arc-agi-3 --force
```

The exact output directory becomes a bundle with this layout:

```text
paper.md
images/
raw/
  main.tex
  expanded.tex
  assets/
  previews/
conversion.json
conversion-report.md
```

`conversion.json` reports `complete` only when every source figure and table
was recovered, every citation and math expression was preserved, and every
media reference resolves to a non-empty local file. Inline and display math use
KaTeX-compatible `$ ... $` and `$$ ... $$` delimiters.
The command exits with status 2 for a partial bundle, which lets callers choose
a whole-document fallback instead of silently accepting degraded Markdown.

## Python API

```python
from pathlib import Path

from latexdl import ConversionRequest, convert_arxiv

result = convert_arxiv(
    ConversionRequest(
        paper="2505.11831",
        output_dir=Path("arc-agi-2"),
    )
)
if not result.report.complete:
    raise RuntimeError(result.report_path)
```

`convert_many()` accepts a sequence of `ConversionRequest` objects and returns
results in the same order.

## Conversion behavior

- arXiv archives are downloaded atomically, size-limited, and extracted without
  trusting archive paths or links.
- Cache keys include the source hash, every output-affecting option, the
  `latexdl` version, and external tool versions.
- LaTeX is expanded in a disposable build copy. Canonical cached sources are
  never polluted with generated files.
- Pandoc's JSON AST is inspected before GitHub-Flavored Markdown is written.
- Extensionless graphics and `\graphicspath` entries are resolved and rewritten
  to bundle-local paths.
- PDF, EPS, and PS figures retain their originals under `raw/assets/` and gain a
  PNG rendering under `images/`.
- Empty or dropped figures and tables are compiled in an offline Bubblewrap
  sandbox. Dropped tables retain both a visual preview and raw LaTeX fallback.

Version 3 intentionally removes the tuple- and `Path`-returning v2 APIs. The
structured request, result, and report models are the only public conversion
interface.
