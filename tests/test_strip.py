from hypothesis import given
from hypothesis import strategies as st

from latexdl.strip import strip


def test_strip_comments(sample_latex):
    """Test that comments are removed."""
    result = strip(sample_latex, strip_comments=True)
    assert "% A comment" not in result
    assert r"\begin{document}" in result


def test_strip_whitespace(sample_latex):
    """Test that excess whitespace is removed."""
    result = strip(sample_latex, strip_whitespace=True)
    assert "text with   extra   whitespace" not in result
    assert "text with extra whitespace" in result


def test_strip_clutter(sample_latex):
    """Test that clutter environments are removed."""
    result = strip(sample_latex, strip_clutter=True)
    assert r"\begin{figure}" not in result
    assert r"\begin{center}" not in result
    assert "Some centered text" not in result


def test_preserve_math(sample_latex_with_math):
    """Test that mathematical content is preserved."""
    result = strip(sample_latex_with_math)
    assert "$x^2 + y^2 = z^2$" in result
    assert r"\[" in result and r"\]" in result
    assert r"\begin{equation}" in result


def test_strip_custom_commands(sample_latex_with_commands):
    """Test that custom command definitions are removed."""
    result = strip(sample_latex_with_commands, strip_clutter=True)
    assert r"\newcommand" not in result
    assert r"\renewcommand" not in result
    assert r"\mycommand{test}" in result
    assert r"\vec{x}" in result


def test_seek_to_document(sample_latex):
    """Test that seeking to document node works."""
    result = strip(sample_latex, seek_to_document_node=True)
    assert r"\documentclass" not in result
    assert r"\usepackage" not in result
    assert r"\begin{document}" in result


@given(st.text())
def test_empty_or_invalid_input(s):
    """Test that the function handles empty or invalid input gracefully."""
    result = strip(s)
    assert isinstance(result, str)


def test_all_features_disabled(sample_latex):
    """Test that no stripping occurs when all features are disabled."""
    result = strip(
        sample_latex,
        strip_comments=False,
        strip_whitespace=False,
        strip_clutter=False,
        seek_to_document_node=False,
    )
    assert "% A comment" in result
    assert "text with   extra   whitespace" in result
    assert r"\begin{figure}" in result
    assert r"\documentclass" in result
