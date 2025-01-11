import argparse
import logging
import re
import shutil
import tarfile
import urllib.parse
from pathlib import Path

import requests
from tqdm import tqdm

from .expand import expand_latex_file
from .strip import strip


def _extract_arxiv_id(package: str) -> str:
    # Approved formats (square brackets denote optional parts):
    # - arXiv ID (e.g., 2103.12345[v#])
    # - Full PDF URL (e.g., https://arxiv.org/pdf/2103.12345[v#][.pdf])
    # - Full Abs URL (e.g., https://arxiv.org/abs/2103.12345[v#])

    if package.startswith("http"):
        # Full URL
        if "pdf" in package:
            # Full PDF URL
            arxiv_id = Path(urllib.parse.urlparse(package).path).name
            if arxiv_id.endswith(".pdf"):
                arxiv_id = arxiv_id[: -len(".pdf")]
        elif "abs" in package:
            # Full Abs URL
            arxiv_id = Path(urllib.parse.urlparse(package).path).name
        else:
            raise ValueError(f"Invalid package URL format: {package}")
    else:
        # arXiv ID
        arxiv_id = package

    return arxiv_id


def _download_and_extract(
    arxiv_id: str,
    output: Path,
    redownload_existing: bool = False,
):
    fpath = output / f"{arxiv_id}.tar.gz"
    if fpath.exists() and not redownload_existing:
        logging.info(f"Package {arxiv_id} already downloaded, skipping")
        return

    url = f"https://arxiv.org/src/{arxiv_id}"
    response = requests.get(url, stream=True)
    response.raise_for_status()

    # Save the response to a file
    with fpath.open("wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    # Extract the tarball
    with tarfile.open(fpath, "r:gz") as tar:
        tar.extractall(output)


def _find_main_latex_file(directory: Path) -> Path | None:
    potential_main_files: list[tuple[Path, float]] = []

    for file_path in directory.rglob("*.[tT][eE][xX]"):  # Case insensitive extension
        score = 0.0

        # Check filename
        if file_path.name.lower() in ["main.tex", "paper.tex", "article.tex"]:
            score += 5

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except UnicodeDecodeError:
            # Skip files that can't be read as UTF-8
            continue

        # Check for \documentclass
        if r"\documentclass" in content:
            score += 3

        # Check for document environment
        if r"\begin{document}" in content and r"\end{document}" in content:
            score += 4

        # Check for multiple \input or \include commands
        if len(re.findall(r"\\(input|include)", content)) > 1:
            score += 2

        # Check for bibliography
        if r"\bibliography" in content or r"\begin{thebibliography}" in content:
            score += 2

        # Consider file size
        score += min(file_path.stat().st_size / 1000, 5)  # Max 5 points for size

        potential_main_files.append((file_path, score))

    # Sort by score in descending order
    potential_main_files.sort(key=lambda x: x[1], reverse=True)

    return potential_main_files[0][0] if potential_main_files else None


def main():
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Download LaTeX packages")
    parser.add_argument("packages", nargs="+", help="Packages to download", type=str)
    parser.add_argument(
        "--output",
        "-o",
        help="Output directory",
        type=Path,
        default=Path.cwd(),
    )
    parser.add_argument(
        "--text",
        help="Use LaTeX2Text to convert to text",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--redownload-existing",
        help="Redownload existing packages",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    parser.add_argument(
        "--force-overwrite",
        help="Force overwrite of existing files",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    args = parser.parse_args()

    output_base: Path = args.output

    # Resolve the packages
    arxiv_ids: list[str] = []
    for package in args.packages:
        assert isinstance(package, str), "Package must be a string"
        arxiv_ids.append(_extract_arxiv_id(package))

    # Process the packages
    for arxiv_id in (pbar := tqdm(arxiv_ids)):
        output = output_base / arxiv_id
        # If the package dir exists, prompt the user
        if output.exists():
            logging.info(f"Output path {output} already exists")
            if not output.is_dir():
                raise ValueError(f"Output path {output} is not a directory")

            if args.force_overwrite:
                # Remove the directory
                logging.warning(f"Removing {output} because of --force-overwrite")
                shutil.rmtree(output)
            else:
                # Otherwise, ask the user
                logging.info(f"Output path {output} already exists")
                resp = input(
                    "Do you want to overwrite it? This will remove all files in the directory. [y/N] "
                ).lower()
                if resp == "y":
                    logging.warning(f"Removing {output}")
                    shutil.rmtree(output)
                else:
                    logging.warning(f"Skipping {arxiv_id}")
                    continue

        # Create the directory
        output.mkdir(parents=True, exist_ok=True)

        # Download and extract the package
        pbar.set_description(f"Downloading {arxiv_id}")
        try:
            _download_and_extract(
                arxiv_id, output, redownload_existing=args.redownload_existing
            )
        except IOError:
            logging.error(f"Error downloading/extracting {arxiv_id}", exc_info=True)
            continue

        # Find the main LaTeX file in the extracted directory
        if (main_file := _find_main_latex_file(output)) is None:
            logging.error(
                f"Could not find the main LaTeX for ID {arxiv_id} (output: {output})"
            )
            continue

        logging.info(f"Resolved main LaTeX file: {main_file}")

        try:
            pbar.set_description(f"Processing {arxiv_id} latex")
            # Expand the LaTeX file (i.e., resolve imports into 1 large file)
            expanded = expand_latex_file(main_file)

            # Convert to text if requested
            if args.text:
                expanded = strip(expanded)

            # Write output
            extension = "txt" if args.text else "tex"
            output_file_path = output_base / f"{arxiv_id}.{extension}"
            pbar.set_description(f"Writing {arxiv_id} to {output_file_path}")
            with output_file_path.open("w", encoding="utf-8") as f:
                f.write(expanded)

        except IOError:
            logging.error(f"Error converting {arxiv_id}", exc_info=True)
            continue


if __name__ == "__main__":
    main()
