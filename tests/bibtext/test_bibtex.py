from __future__ import annotations

import re

import pytest

from latexdl._bibtex import (
    BIBLIOGRAPHY_PATTERNS,
    CITATION_PATTERNS,
    _extract_manual_bibliography,
    _remove_unreferenced_keys,
    detect_and_collect_bibtex,
)

# Test data
SAMPLE_BIBTEX = """@article{smith2020,
  author = {Smith, John},
  title = {Sample Article},
  journal = {Journal of Examples},
  year = {2020},
}

@book{jones2019,
  author = {Jones, Alice},
  title = {Example Book},
  publisher = {Sample Publisher},
  year = {2019},
}
"""

SAMPLE_BIBLATEX = """@article{wilson2021,
  author = {Wilson, Bob},
  title = {Biblatex Example},
  journal = {Journal of Testing},
  year = {2021},
}
"""

MANUAL_BIBLIOGRAPHY = r"""
\begin{thebibliography}{99}
\bibitem{manual2018} Johnson, M. (2018). Manual Entry. Journal of Tests, 10(2).
\bibitem{another2017} Williams, T. (2017). Another Entry. Testing Journal.
\end{thebibliography}
"""


class TestBibliographyPatterns:
    """Test the bibliography file detection patterns"""

    @pytest.mark.parametrize(
        "command,filename",
        [
            (r"\bibliography{refs}", "refs"),
            (r"\bibliography{sample,refs}", "sample,refs"),
            (r"\addbibresource{refs.bib}", "refs.bib"),
            (r"\nobibliography{extra}", "extra"),
        ],
    )
    def test_bibliography_patterns(self, command, filename):
        """Test that bibliography patterns correctly match various commands"""
        for pattern in BIBLIOGRAPHY_PATTERNS:
            match = re.search(pattern, command)
            if match:
                assert match.group(1) == filename
                return
        assert False, f"No pattern matched for {command}"


class TestCitationPatterns:
    """Test the citation command detection patterns"""

    @pytest.mark.parametrize(
        "command,keys",
        [
            (r"\cite{smith2020}", "smith2020"),
            (r"\citep{jones2019}", "jones2019"),
            (r"\citet{smith2020,jones2019}", "smith2020,jones2019"),
            (r"\parencite{wilson2021}", "wilson2021"),
            (r"\textcite{manual2018}", "manual2018"),
            (r"\footcite{another2017}", "another2017"),
            (r"\autocite{smith2020}", "smith2020"),
            (r"\citeauthor{jones2019}", "jones2019"),
            (r"\citeyear{wilson2021}", "wilson2021"),
            (r"\cites[see][p.~34]{smith2020}[also][]{jones2019}", "smith2020"),
            (r"\parencites{smith2020}{jones2019}", "smith2020"),
            (r"\cite*{smith2020}", "smith2020"),
        ],
    )
    def test_citation_patterns(self, command, keys):
        """Test that citation patterns correctly match various commands"""
        for pattern in CITATION_PATTERNS:
            match = re.search(pattern, command)
            if match:
                assert match.group(1) == keys
                return
        assert False, f"No pattern matched for {command}"


class TestManualBibliography:
    """Test the manual bibliography extraction function"""

    def test_extract_manual_bibliography(self):
        """Test that manual bibliographies are correctly extracted"""
        entries = _extract_manual_bibliography(MANUAL_BIBLIOGRAPHY)
        assert len(entries) == 2
        assert "manual2018" in entries
        assert "another2017" in entries
        assert "Johnson" in entries["manual2018"]
        assert "Williams" in entries["another2017"]


class TestRemoveUnreferencedKeys:
    """Test the function to remove unreferenced keys"""

    def test_remove_unreferenced_keys(self):
        """Test that unreferenced keys are correctly removed"""
        entries = {
            "smith2020": "- @smith2020: Smith paper",
            "jones2019": "- @jones2019: Jones book",
            "wilson2021": "- @wilson2021: Wilson article",
            "unused2022": "- @unused2022: Unused entry",
        }

        latex_content = r"""
        This is a sample latex document.
        \cite{smith2020}
        Also see \parencite{wilson2021} and \textcite{jones2019}.
        """

        result = _remove_unreferenced_keys(entries, latex_content)
        assert len(result) == 3
        assert "smith2020" in result
        assert "jones2019" in result
        assert "wilson2021" in result
        assert "unused2022" not in result


@pytest.fixture
def mock_bibtex_file(tmp_path):
    """Create a temporary BibTeX file for testing"""
    bib_file = tmp_path / "refs.bib"
    bib_file.write_text(SAMPLE_BIBTEX)
    return bib_file


@pytest.fixture
def mock_biblatex_file(tmp_path):
    """Create a temporary BibLaTeX file for testing"""
    bib_file = tmp_path / "extra.bib"
    bib_file.write_text(SAMPLE_BIBLATEX)
    return bib_file


class TestDetectAndCollectBibtex:
    """Integration tests for the main bibtex collection function"""

    def test_standard_bibliography(self, tmp_path, mock_bibtex_file):
        """Test with standard \bibliography command"""
        latex_content = r"""
        \documentclass{article}
        \begin{document}
        This cites \cite{smith2020} and \cite{jones2019}.
        \bibliography{refs}
        \end{document}
        """

        result = detect_and_collect_bibtex(tmp_path, latex_content)
        assert result is not None
        assert "smith2020" in result
        assert "jones2019" in result

    def test_biblatex_addbibresource(self, tmp_path, mock_biblatex_file):
        """Test with biblatex's \addbibresource command"""
        latex_content = r"""
        \documentclass{article}
        \usepackage{biblatex}
        \addbibresource{extra.bib}
        \begin{document}
        This cites \cite{wilson2021}.
        \printbibliography
        \end{document}
        """

        result = detect_and_collect_bibtex(tmp_path, latex_content)
        assert result is not None
        assert "wilson2021" in result

    def test_multiple_bibliography_files(
        self, tmp_path, mock_bibtex_file, mock_biblatex_file
    ):
        """Test with multiple bibliography files"""
        latex_content = r"""
        \documentclass{article}
        \begin{document}
        This cites \cite{smith2020} and \cite{wilson2021}.
        \bibliography{refs,extra}
        \end{document}
        """

        # Create an extra.bib file with the BibLaTeX content
        (tmp_path / "extra.bib").write_text(SAMPLE_BIBLATEX)

        result = detect_and_collect_bibtex(tmp_path, latex_content)
        assert result is not None
        assert "smith2020" in result
        assert "wilson2021" in result

    def test_with_manual_bibliography(self, tmp_path):
        """Test with a manual bibliography environment"""
        latex_content = (
            r"""
        \documentclass{article}
        \begin{document}
        This cites \cite{manual2018} and \cite{another2017}.
        """
            + MANUAL_BIBLIOGRAPHY
            + r"""
        \end{document}
        """
        )

        result = detect_and_collect_bibtex(tmp_path, latex_content)
        assert result is not None
        assert "manual2018" in result
        assert "another2017" in result

    def test_complex_citations(self, tmp_path, mock_bibtex_file):
        """Test with complex citation commands"""
        latex_content = r"""
        \documentclass{article}
        \begin{document}
        Basic \cite{smith2020}
        Parenthetical \citep{jones2019}
        Textual \citet{smith2020}
        Multiple \cite{smith2020,jones2019}
        With notes \cite[p.42]{smith2020}
        Biblatex \parencite{jones2019}
        Multiple biblatex \parencites{smith2020}{jones2019}
        Author only \citeauthor{smith2020}
        Year only \citeyear{jones2019}
        \bibliography{refs}
        \end{document}
        """

        result = detect_and_collect_bibtex(tmp_path, latex_content)
        assert result is not None
        assert "smith2020" in result
        assert "jones2019" in result

    def test_unreferenced_removal(self, tmp_path, mock_bibtex_file):
        """Test removal of unreferenced entries"""
        latex_content = r"""
        \documentclass{article}
        \begin{document}
        This only cites \cite{smith2020}.
        \bibliography{refs}
        \end{document}
        """

        result = detect_and_collect_bibtex(
            tmp_path, latex_content, remove_unreferenced=True
        )
        assert result is not None
        assert "smith2020" in result
        assert "jones2019" not in result

    def test_no_removal_of_unreferenced(self, tmp_path, mock_bibtex_file):
        """Test keeping unreferenced entries when requested"""
        latex_content = r"""
        \documentclass{article}
        \begin{document}
        This only cites \cite{smith2020}.
        \bibliography{refs}
        \end{document}
        """

        result = detect_and_collect_bibtex(
            tmp_path, latex_content, remove_unreferenced=False
        )
        assert result is not None
        assert "smith2020" in result
        assert "jones2019" in result
