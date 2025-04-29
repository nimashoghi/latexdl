from __future__ import annotations

from pathlib import Path

import pytest

from latexdl._bibtex import detect_and_collect_bibtex

from .test_bibtex_data import complex_latex_project as complex_latex_project


@pytest.mark.parametrize("use_case", ["standard", "biblatex", "manual"])
def test_integration_with_complex_project(complex_latex_project, use_case, monkeypatch):
    """Test the bibliography detection with a complex project structure"""
    project_dir = Path(complex_latex_project)

    # Mock the expand_latex_file function to avoid need for actual latexpand utility
    def mock_expand(f_in, *, keep_comments):
        if use_case == "standard":
            return (
                (project_dir / "main.tex").read_text()
                + (project_dir / "sections" / "introduction.tex").read_text()
                + (project_dir / "sections" / "methods.tex").read_text()
            )
        elif use_case == "biblatex":
            return (project_dir / "biblatex_project" / "document.tex").read_text()
        elif use_case == "manual":
            return (project_dir / "manual_bib" / "manual.tex").read_text()
        else:
            raise ValueError(f"Unknown use case: {use_case}")

    monkeypatch.setattr("latexdl.expand.expand_latex_file", mock_expand)

    # Run the tests for each type of LaTeX project
    if use_case == "standard":
        main_file = project_dir / "main.tex"
        latex_content = mock_expand(main_file, keep_comments=False)
        result = detect_and_collect_bibtex(project_dir, latex_content)

        # Verify results
        assert result is not None
        # Check for references from main file
        assert "smith2020" in result
        assert "jones2019" in result
        assert "brown2021" in result
        assert "davis2018" in result
        assert "multi2022" in result
        # Check for references from included sections
        assert "wilson2017" in result
        assert "zhang2019" in result
        assert "taylor2020" in result
        assert "stats2019" in result
        assert "stats2020" in result
        # Check unused references are removed
        assert "unused2023" not in result
        assert "another_unused" not in result

    elif use_case == "biblatex":
        main_file = project_dir / "biblatex_project" / "document.tex"
        latex_content = mock_expand(main_file, keep_comments=False)

        # Mock handling for addbibresource which expects full path
        original_detect = detect_and_collect_bibtex

        def patched_detect(base_dir, expanded_contents, **kwargs):
            # Replace addbibresource with bibliography for testing
            modified_content = expanded_contents.replace(
                r"\addbibresource{biblatex_refs.bib}", r"\bibliography{biblatex_refs}"
            )
            return original_detect(base_dir, modified_content, **kwargs)

        monkeypatch.setattr("latexdl._bibtex.detect_and_collect_bibtex", patched_detect)

        result = patched_detect(project_dir / "biblatex_project", latex_content)

        # Verify results
        assert result is not None
        # Check for biblatex references
        assert "anderson2021" in result
        assert "roberts2019" in result
        assert "white2020" in result
        assert "martin2018" in result
        assert "lee2017" in result
        assert "parker2019" in result
        # Check unused reference is removed
        assert "unused_biblatex" not in result

    elif use_case == "manual":
        main_file = project_dir / "manual_bib" / "manual.tex"
        latex_content = mock_expand(main_file, keep_comments=False)
        result = detect_and_collect_bibtex(project_dir / "manual_bib", latex_content)

        # Verify results
        assert result is not None
        # Check for manual bibliography entries
        assert "manual2018" in result
        assert "another2017" in result
        # Check unused entry is removed
        assert "unused_manual" not in result


def test_realistic_project_simulation(tmp_path, monkeypatch):
    """
    Test with a more realistic project simulation that combines
    different citation styles and bibliography types
    """
    # Create a mixed project with multiple bibliography types
    project_dir = tmp_path / "mixed_project"
    project_dir.mkdir()

    # Main LaTeX file
    main_content = r"""
\documentclass{article}
\usepackage{natbib}
\usepackage{biblatex}

\addbibresource{modern_refs.bib}
\bibliography{classic_refs}

\begin{document}
% Traditional citations
Classic citation \cite{classic2020}
Natbib citation \citep{natbib2019}

% Biblatex citations
Modern citation \parencite{modern2021}
Text citation \textcite{modern2018}

% Manual references
Manual citation \cite{manual2017}

\begin{thebibliography}{99}
\bibitem{manual2017} Manual, Author. (2017). Manual Entry Title. Journal of Manual Entries.
\end{thebibliography}

\printbibliography
\end{document}
"""
    (project_dir / "main.tex").write_text(main_content)

    # Create bibliography files
    classic_refs_content = """
@article{classic2020,
  author = {Classic, Author},
  title = {Classic Citation Style},
  journal = {Traditional Journal},
  year = {2020},
}

@book{natbib2019,
  author = {Natbib, Writer},
  title = {Natbib Citation Book},
  publisher = {Citation Press},
  year = {2019},
}

@article{unused_classic,
  author = {Unused, Again},
  title = {Never Used Classic},
  journal = {Ignored Classic},
  year = {2018},
}
"""
    (project_dir / "classic_refs.bib").write_text(classic_refs_content)

    modern_refs_content = """
@article{modern2021,
  author = {Modern, Researcher},
  title = {Modern Citation Approach},
  journal = {Contemporary Journal},
  year = {2021},
}

@inproceedings{modern2018,
  author = {Text, Citation},
  title = {Text Citation Example},
  booktitle = {Proceedings of Citation Conference},
  year = {2018},
}

@article{unused_modern,
  author = {Never, Referenced},
  title = {Unused Modern Reference},
  journal = {Modern Ignored},
  year = {2020},
}
"""
    (project_dir / "modern_refs.bib").write_text(modern_refs_content)

    # Mock expand_latex_file
    def mock_expand(f_in, *, keep_comments):
        return main_content

    monkeypatch.setattr("latexdl.expand.expand_latex_file", mock_expand)

    # Test detection
    result = detect_and_collect_bibtex(project_dir, main_content)

    # Verify results
    assert result is not None
    # Check classic references
    assert "classic2020" in result
    assert "natbib2019" in result
    # Check modern references
    assert "modern2021" in result
    assert "modern2018" in result
    # Check manual reference
    assert "manual2017" in result
    # Check unused references are excluded
    assert "unused_classic" not in result
    assert "unused_modern" not in result
