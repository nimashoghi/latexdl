from __future__ import annotations

from pathlib import Path

from latexdl._assets import AssetManager, detect_media_type, media_targets
from latexdl.models import Diagnostic


def _manager(
    tmp_path: Path, expanded: str = ""
) -> tuple[AssetManager, Path, Path, list[Diagnostic]]:
    source = tmp_path / "source"
    bundle = tmp_path / "bundle"
    source.mkdir()
    (bundle / "images").mkdir(parents=True)
    (bundle / "raw").mkdir()
    main = source / "main.tex"
    main.write_text("source")
    diagnostics: list[Diagnostic] = []
    manager = AssetManager(
        source_dir=source,
        main_file=main,
        bundle_dir=bundle,
        expanded_latex=expanded,
        render_dpi=120,
        timeout_seconds=10,
        diagnostics=diagnostics,
    )
    return manager, source, bundle, diagnostics


def test_media_targets_handles_markdown_img_and_embed() -> None:
    markdown = """
![one](images/one.png)
<img src="images/two.jpg" width="50%" />
<embed src='raw/three.pdf' />
"""
    assert media_targets(markdown) == [
        "images/one.png",
        "images/two.jpg",
        "raw/three.pdf",
    ]


def test_detect_media_type_recognizes_real_png_signature(tmp_path: Path) -> None:
    image = tmp_path / "extensionless"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"payload")
    assert detect_media_type(image) == "image/png"


def test_rewrite_resolves_extensionless_html_and_markdown_targets(
    tmp_path: Path,
) -> None:
    manager, source, bundle, diagnostics = _manager(tmp_path)
    (source / "figure.png").write_bytes(b"\x89PNG\r\n\x1a\nimage")

    rewritten = manager.rewrite_markdown(
        '<figure><img src="figure" /></figure>\n\n![same](figure)\n'
    )

    assert rewritten.count("images/figure.png") == 2
    assert (bundle / "images" / "figure.png").is_file()
    assert len(manager.records) == 1
    assert diagnostics == []


def test_rewrite_honors_graphicspath(tmp_path: Path) -> None:
    expanded = r"\graphicspath{{plots/}{other/}}"
    manager, source, bundle, diagnostics = _manager(tmp_path, expanded)
    (source / "plots").mkdir()
    (source / "plots" / "curve.jpg").write_bytes(b"\xff\xd8\xffimage")

    rewritten = manager.rewrite_markdown("![](curve)")

    assert rewritten == "![](images/curve.jpg)"
    assert (bundle / "images" / "curve.jpg").is_file()
    assert diagnostics == []


def test_rewrite_reports_missing_and_unsafe_media(tmp_path: Path) -> None:
    manager, _source, _bundle, diagnostics = _manager(tmp_path)

    rewritten = manager.rewrite_markdown(
        "![](missing.png)\n![](../escape.png)\n![](https://example.com/image.png)"
    )

    assert "missing.png" in rewritten
    assert {item.code for item in diagnostics} == {
        "missing-media",
        "remote-media",
        "unsafe-media-path",
    }


def test_pdf_is_retained_and_rendered_to_png(tmp_path: Path, monkeypatch) -> None:
    manager, source, bundle, diagnostics = _manager(tmp_path)
    (source / "diagram.pdf").write_bytes(b"%PDF-1.7\nsource")

    def fake_run(command: list[str], *, cwd: Path, timeout_seconds: int):
        del timeout_seconds
        assert command[0] == "pdftocairo"
        (cwd / f"{command[-1]}.png").write_bytes(b"\x89PNG\r\n\x1a\nrender")

    monkeypatch.setattr("latexdl._assets.run_sandboxed", fake_run)

    rewritten = manager.rewrite_markdown('<embed src="diagram.pdf" />')

    assert rewritten == '<embed src="images/diagram.png" />'
    assert (bundle / "images" / "diagram.png").is_file()
    assert (bundle / "raw" / "assets" / "diagram.pdf").is_file()
    assert manager.records[0].raw_output == "raw/assets/diagram.pdf"
    assert diagnostics == []


def test_validate_rejects_zero_byte_asset(tmp_path: Path) -> None:
    manager, _source, bundle, diagnostics = _manager(tmp_path)
    empty = bundle / "images" / "empty.png"
    empty.touch()

    assert manager.validate_markdown("![](images/empty.png)") == 1
    assert diagnostics[-1].code == "invalid-bundled-media"
