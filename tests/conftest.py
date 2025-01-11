from pathlib import Path

import pytest


@pytest.fixture
def test_files_dir():
    """Fixture that provides path to test files directory."""
    return Path(__file__).parent / "test_files"


@pytest.fixture
def sample_latex():
    """Fixture that provides a basic LaTeX document."""
    return r"""
\documentclass{article}
\usepackage{graphicx}

% A comment
\begin{document}

Some text with   extra   whitespace.

\begin{figure}
    \includegraphics{image.png}
    \caption{A figure}
\end{figure}

\begin{center}
Some centered text
\end{center}

\end{document}
"""


@pytest.fixture
def sample_latex_with_math():
    """Fixture that provides a LaTeX document with math."""
    return r"""
\documentclass{article}
\usepackage{amsmath}

\begin{document}

Inline math: $x^2 + y^2 = z^2$

Display math:
\[
    E = mc^2
\]

Equation environment:
\begin{equation}
    f(x) = \int_0^x g(t)\,dt
\end{equation}

\end{document}
"""


@pytest.fixture
def sample_latex_with_commands():
    """Fixture that provides a LaTeX document with custom commands."""
    return r"""
\documentclass{article}

\newcommand{\mycommand}[1]{#1}
\renewcommand{\vec}[1]{\mathbf{#1}}

\begin{document}
\mycommand{test}
\vec{x}
\end{document}
"""
