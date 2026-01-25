from __future__ import annotations

import pytest
from pathlib import Path

from latexdl._assets import (
    _parse_image_references,
    _resolve_image_path,
    copy_assets,
)


class TestParseImageReferences:
    def test_markdown_simple(self):
        content = "![Alt text](image.png)"
        refs = _parse_image_references(content, markdown=True)
        assert refs == ["image.png"]

    def test_markdown_multiple(self):
        content = """
        ![Figure 1](figures/fig1.pdf)
        Some text here
        ![Figure 2](images/diagram.png)
        """
        refs = _parse_image_references(content, markdown=True)
        assert refs == ["figures/fig1.pdf", "images/diagram.png"]

    def test_markdown_empty_alt(self):
        content = "![](plot.svg)"
        refs = _parse_image_references(content, markdown=True)
        assert refs == ["plot.svg"]

    def test_markdown_complex_alt(self):
        # In practice, pandoc output doesn't nest markdown syntax in alt text
        content = "![Complex alt text here](image.jpg)"
        refs = _parse_image_references(content, markdown=True)
        assert refs == ["image.jpg"]

    def test_latex_simple(self):
        content = r"\includegraphics{figure.pdf}"
        refs = _parse_image_references(content, markdown=False)
        assert refs == ["figure.pdf"]

    def test_latex_with_options(self):
        content = r"\includegraphics[width=0.8\textwidth]{figures/diagram}"
        refs = _parse_image_references(content, markdown=False)
        assert refs == ["figures/diagram"]

    def test_latex_multiple(self):
        content = r"""
        \includegraphics{fig1.pdf}
        \includegraphics[scale=0.5]{fig2.png}
        \includegraphics[width=\columnwidth,height=5cm]{subfolder/fig3}
        """
        refs = _parse_image_references(content, markdown=False)
        assert refs == ["fig1.pdf", "fig2.png", "subfolder/fig3"]

    def test_no_images(self):
        content = "This is just text with no images."
        assert _parse_image_references(content, markdown=True) == []
        assert _parse_image_references(content, markdown=False) == []

    def test_html_embed_tags(self):
        # Pandoc sometimes outputs HTML embed tags for figures
        content = '<embed src="figures/overview.pdf" />'
        refs = _parse_image_references(content, markdown=True)
        assert refs == ["figures/overview.pdf"]

    def test_mixed_markdown_and_embed(self):
        content = """
        <embed src="figures/overview.pdf" />
        ![Figure 1](images/plot.png)
        <embed src="figures/diagram.pdf" />
        """
        refs = _parse_image_references(content, markdown=True)
        assert "images/plot.png" in refs
        assert "figures/overview.pdf" in refs
        assert "figures/diagram.pdf" in refs
        assert len(refs) == 3


class TestResolveImagePath:
    def test_exact_path(self, tmp_path: Path):
        image_file = tmp_path / "figure.png"
        image_file.write_bytes(b"fake image")

        result = _resolve_image_path(tmp_path, "figure.png")
        assert result == image_file

    def test_path_with_extension_search(self, tmp_path: Path):
        # LaTeX often omits extensions
        image_file = tmp_path / "figure.pdf"
        image_file.write_bytes(b"fake pdf")

        result = _resolve_image_path(tmp_path, "figure")
        assert result == image_file

    def test_subdirectory(self, tmp_path: Path):
        subdir = tmp_path / "figures"
        subdir.mkdir()
        image_file = subdir / "plot.png"
        image_file.write_bytes(b"fake image")

        result = _resolve_image_path(tmp_path, "figures/plot.png")
        assert result == image_file

    def test_subdirectory_without_extension(self, tmp_path: Path):
        subdir = tmp_path / "images"
        subdir.mkdir()
        image_file = subdir / "diagram.eps"
        image_file.write_bytes(b"fake eps")

        result = _resolve_image_path(tmp_path, "images/diagram")
        assert result == image_file

    def test_leading_dot_slash(self, tmp_path: Path):
        image_file = tmp_path / "image.png"
        image_file.write_bytes(b"fake image")

        result = _resolve_image_path(tmp_path, "./image.png")
        assert result == image_file

    def test_not_found(self, tmp_path: Path):
        result = _resolve_image_path(tmp_path, "nonexistent.png")
        assert result is None

    def test_extension_priority(self, tmp_path: Path):
        # Create multiple files with same base name
        (tmp_path / "figure.pdf").write_bytes(b"pdf")
        (tmp_path / "figure.png").write_bytes(b"png")

        # PDF should be found first (comes first in extension list)
        result = _resolve_image_path(tmp_path, "figure")
        assert result == tmp_path / "figure.pdf"


class TestCopyAssets:
    def test_copy_markdown_images(self, tmp_path: Path):
        source_dir = tmp_path / "source"
        output_dir = tmp_path / "output"
        source_dir.mkdir()

        # Create source image
        (source_dir / "image.png").write_bytes(b"fake image data")

        content = "![Alt](image.png)"
        copy_assets(source_dir, output_dir, content, markdown=True)

        assert (output_dir / "image.png").exists()
        assert (output_dir / "image.png").read_bytes() == b"fake image data"

    def test_copy_preserves_directory_structure(self, tmp_path: Path):
        source_dir = tmp_path / "source"
        output_dir = tmp_path / "output"
        source_dir.mkdir()

        # Create nested structure
        (source_dir / "figures").mkdir()
        (source_dir / "figures" / "plot.pdf").write_bytes(b"pdf data")

        content = "![](figures/plot.pdf)"
        copy_assets(source_dir, output_dir, content, markdown=True)

        assert (output_dir / "figures" / "plot.pdf").exists()

    def test_copy_latex_images(self, tmp_path: Path):
        source_dir = tmp_path / "source"
        output_dir = tmp_path / "output"
        source_dir.mkdir()

        (source_dir / "diagram.eps").write_bytes(b"eps data")

        content = r"\includegraphics[width=0.5\textwidth]{diagram.eps}"
        copy_assets(source_dir, output_dir, content, markdown=False)

        assert (output_dir / "diagram.eps").exists()

    def test_skip_missing_images(self, tmp_path: Path):
        source_dir = tmp_path / "source"
        output_dir = tmp_path / "output"
        source_dir.mkdir()

        content = "![](nonexistent.png)"
        # Should not raise, just log a warning
        copy_assets(source_dir, output_dir, content, markdown=True)

        # Output dir may or may not exist (no files to copy)
        assert not (output_dir / "nonexistent.png").exists()

    def test_skip_already_existing(self, tmp_path: Path):
        source_dir = tmp_path / "source"
        output_dir = tmp_path / "output"
        source_dir.mkdir()
        output_dir.mkdir()

        (source_dir / "image.png").write_bytes(b"source data")
        (output_dir / "image.png").write_bytes(b"existing data")

        content = "![](image.png)"
        copy_assets(source_dir, output_dir, content, markdown=True)

        # Should not overwrite existing file
        assert (output_dir / "image.png").read_bytes() == b"existing data"

    def test_no_images_in_content(self, tmp_path: Path):
        source_dir = tmp_path / "source"
        output_dir = tmp_path / "output"
        source_dir.mkdir()

        content = "Just text, no images."
        copy_assets(source_dir, output_dir, content, markdown=True)

        # Should complete without error, output_dir may not even be created

    def test_resolve_missing_extension(self, tmp_path: Path):
        source_dir = tmp_path / "source"
        output_dir = tmp_path / "output"
        source_dir.mkdir()

        # Create image with extension
        (source_dir / "figure.pdf").write_bytes(b"pdf data")

        # LaTeX reference without extension
        content = r"\includegraphics{figure}"
        copy_assets(source_dir, output_dir, content, markdown=False)

        # Should find and copy the .pdf file
        assert (output_dir / "figure.pdf").exists()
