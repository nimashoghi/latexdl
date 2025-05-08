from __future__ import annotations

import logging
import pickle
from pathlib import Path

import pydantic

from ._types import ArxivMetadata

log = logging.getLogger(__name__)

CACHE_VERSION = 1
CACHE_FILE_NAME = "cache.json"


class CacheContent(pydantic.BaseModel):
    cache_version: int
    paper_contents: str
    metadata: ArxivMetadata | None


def load_cache(working_dir: Path):
    if not (cache_file := working_dir / CACHE_FILE_NAME).exists():
        return None

    try:
        with cache_file.open("r") as f:
            cache = CacheContent.model_validate_json(f.read())

    except pydantic.ValidationError as e:
        log.warning(
            f"Cache file {cache_file} is corrupted. "
            f"Error: {e}. Deleting the cache file."
        )
        cache_file.unlink()
        return None

    if cache.cache_version != CACHE_VERSION:
        log.warning(
            f"Cache file {cache_file} is outdated. "
            f"Expected version: {CACHE_VERSION}, found: {cache.cache_version}. "
            f"Deleting the cache file."
        )
        cache_file.unlink()
        return None

    return cache


def save_cache(
    working_dir: Path,
    paper_contents: str,
    metadata: ArxivMetadata | None,
):
    cache_file = working_dir / CACHE_FILE_NAME
    cache = CacheContent(
        cache_version=CACHE_VERSION,
        paper_contents=paper_contents,
        metadata=metadata,
    )

    with cache_file.open("w") as f:
        f.write(cache.model_dump_json(indent=4))
