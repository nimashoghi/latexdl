from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def complex_latex_project():
    """Create a complex LaTeX project structure with multiple bibliography styles"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Create project structure
        project_dir = Path(tmp_dir)
        sections_dir = project_dir / "sections"
        sections_dir.mkdir()

        # Create main.tex
        main_content = r"""
\documentclass{article}
\usepackage{cite}
\usepackage{natbib}
\begin{document}
\input{sections/introduction}
\input{sections/methods}

Standard citation \cite{smith2020}
Parenthetical citation \citep{jones2019}
Textual citation \citet{brown2021}
With page number \cite[p.42]{davis2018}
Abbreviated author list \citet*{multi2022}
Multiple citations \cite{smith2020,jones2019,brown2021}

\bibliography{references,extra_refs}
\end{document}
"""
        (project_dir / "main.tex").write_text(main_content)

        # Create section files
        intro_content = r"""
\section{Introduction}
As stated by \citeauthor{wilson2017}, this is an important area of research \cite{wilson2017}.
The methodology builds on previous work \citep{zhang2019}.
"""
        (sections_dir / "introduction.tex").write_text(intro_content)

        methods_content = r"""
\section{Methods}
We follow the approach described in \citet{taylor2020} with modifications.
For statistical analysis, multiple methods were used \cite{stats2019,stats2020}.
"""
        (sections_dir / "methods.tex").write_text(methods_content)

        # Create bibliography files
        references_content = """
@article{smith2020,
  author = {Smith, John},
  title = {Sample Article},
  journal = {Journal of Examples},
  year = {2020},
}

@book{jones2019,
  author = {Jones, Alice},
  title = {Example Book},
  publisher = {Example Press},
  year = {2019},
}

@article{brown2021,
  author = {Brown, Robert},
  title = {Test Article},
  journal = {Testing Journal},
  year = {2021},
}

@inproceedings{davis2018,
  author = {Davis, Emma},
  title = {Conference Paper},
  booktitle = {Proceedings of the Example Conference},
  year = {2018},
}

@article{multi2022,
  author = {Johnson, Tim and Williams, Sarah and Miller, James and Brown, David and Smith, Michael},
  title = {Multi-author Paper},
  journal = {Collaboration Journal},
  year = {2022},
}

@article{unused2023,
  author = {Unused, Author},
  title = {Never Cited Paper},
  journal = {Ignored Journal},
  year = {2023},
}
"""
        (project_dir / "references.bib").write_text(references_content)

        extra_refs_content = """
@article{wilson2017,
  author = {Wilson, Bob},
  title = {Important Research},
  journal = {Research Journal},
  year = {2017},
}

@article{zhang2019,
  author = {Zhang, Li},
  title = {Previous Work},
  journal = {Foundation Journal},
  year = {2019},
}

@article{taylor2020,
  author = {Taylor, Anne},
  title = {Methodological Approach},
  journal = {Methods Today},
  year = {2020},
}

@article{stats2019,
  author = {Thompson, Mark},
  title = {Statistical Method One},
  journal = {Statistics Journal},
  year = {2019},
}

@article{stats2020,
  author = {Harris, Patricia},
  title = {Statistical Method Two},
  journal = {Advanced Statistics},
  year = {2020},
}

@article{another_unused,
  author = {Never, Used},
  title = {Another Unused Reference},
  journal = {Forgotten Journal},
  year = {2018},
}
"""
        (project_dir / "extra_refs.bib").write_text(extra_refs_content)

        # Create biblatex project
        biblatex_dir = project_dir / "biblatex_project"
        biblatex_dir.mkdir()

        biblatex_content = r"""
\documentclass{article}
\usepackage[style=authoryear]{biblatex}
\addbibresource{biblatex_refs.bib}

\begin{document}
Regular citation \cite{anderson2021}
Parenthetical \parencite{roberts2019}
Textual \textcite{white2020}
Footnote citation \footcite{martin2018}
Superscript citation \supercite{lee2017}
Full citation \fullcite{parker2019}
Multiple \cites(see)(p.~42){anderson2021}(also)(p.~15){roberts2019}

\printbibliography
\end{document}
"""
        (biblatex_dir / "document.tex").write_text(biblatex_content)

        biblatex_refs_content = """
@book{anderson2021,
  author = {Anderson, James},
  title = {Biblatex Book},
  publisher = {Academic Press},
  year = {2021},
}

@article{roberts2019,
  author = {Roberts, Susan},
  title = {Biblatex Article},
  journal = {Biblatex Journal},
  year = {2019},
}

@inproceedings{white2020,
  author = {White, Thomas},
  title = {Biblatex Conference Paper},
  booktitle = {Proceedings of the Biblatex Conference},
  year = {2020},
}

@book{martin2018,
  author = {Martin, Emily},
  title = {Footnote Example},
  publisher = {Testing Press},
  year = {2018},
}

@article{lee2017,
  author = {Lee, Daniel},
  title = {Superscript Example},
  journal = {Format Journal},
  year = {2017},
}

@book{parker2019,
  author = {Parker, Matthew},
  title = {Full Citation Example},
  publisher = {Complete Press},
  year = {2019},
}

@article{unused_biblatex,
  author = {Unused, Again},
  title = {Never Referenced Paper},
  journal = {Ignored Again},
  year = {2020},
}
"""
        (biblatex_dir / "biblatex_refs.bib").write_text(biblatex_refs_content)

        # Create manual bibliography project
        manual_dir = project_dir / "manual_bib"
        manual_dir.mkdir()

        manual_content = r"""
\documentclass{article}
\begin{document}
As shown by \cite{manual2018}, this approach works.
Also see \cite{another2017} for more details.

\begin{thebibliography}{99}
\bibitem{manual2018} Johnson, M. (2018). Manual Entry. Journal of Tests, 10(2).
\bibitem{another2017} Williams, T. (2017). Another Entry. Testing Journal.
\bibitem{unused_manual} Unused, A. (2019). Never Cited. Ignored Again.
\end{thebibliography}
\end{document}
"""
        (manual_dir / "manual.tex").write_text(manual_content)

        # Return the project path
        yield str(project_dir)
