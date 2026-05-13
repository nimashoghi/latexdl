from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, ClassVar

import pytest

from latexdl import _metadata


@dataclass(frozen=True)
class FakeAuthor:
    name: str


@dataclass(frozen=True)
class FakePaper:
    title: str = "A Test Paper"
    authors: tuple[FakeAuthor, ...] = (FakeAuthor("Ada Lovelace"),)
    published: dt.datetime | None = dt.datetime(2024, 1, 2, tzinfo=dt.timezone.utc)
    summary: str = "A short abstract."
    entry_id: str = "https://arxiv.org/abs/2401.00001v1"
    pdf_url: str | None = "https://arxiv.org/pdf/2401.00001v1"


class FakeClient:
    query_url_format = _metadata._ARXIV_API_QUERY_URL_FORMATS[0]
    calls: ClassVar[list[tuple[str, list[str], int | None, int]]] = []
    responses: ClassVar[dict[str, list[FakePaper] | Exception]] = {}

    def __init__(
        self,
        page_size: int = 100,
        delay_seconds: float = 3.0,
        num_retries: int = 3,
    ) -> None:
        del delay_seconds, num_retries
        self.page_size = page_size
        self.query_url_format = type(self).query_url_format

    def results(self, search: Any) -> Any:
        type(self).calls.append(
            (
                self.query_url_format,
                list(search.id_list),
                search.max_results,
                self.page_size,
            )
        )
        response = type(self).responses[self.query_url_format]
        if isinstance(response, Exception):
            raise response
        return iter(response)


@pytest.fixture(autouse=True)
def fake_arxiv_client(monkeypatch: pytest.MonkeyPatch) -> type[FakeClient]:
    FakeClient.calls = []
    FakeClient.responses = {}
    monkeypatch.setattr(_metadata.arxiv, "Client", FakeClient)
    return FakeClient


def test_fetch_arxiv_metadata_falls_back_to_regular_arxiv_on_export_failure() -> None:
    export_url, regular_url = _metadata._ARXIV_API_QUERY_URL_FORMATS
    FakeClient.responses = {
        export_url: RuntimeError("HTTP 429"),
        regular_url: [FakePaper()],
    }

    metadata = _metadata.fetch_arxiv_metadata("2401.00001v2")

    assert metadata is not None
    assert metadata.title == "A Test Paper"
    assert metadata.authors == ["Ada Lovelace"]
    assert metadata.published == dt.date(2024, 1, 2)
    assert FakeClient.calls == [
        (export_url, ["2401.00001"], 1, 1),
        (regular_url, ["2401.00001"], 1, 1),
    ]


def test_fetch_arxiv_metadata_uses_export_when_it_succeeds() -> None:
    export_url, regular_url = _metadata._ARXIV_API_QUERY_URL_FORMATS
    FakeClient.responses = {
        export_url: [FakePaper(title="Primary Host")],
        regular_url: [FakePaper(title="Fallback Host")],
    }

    metadata = _metadata.fetch_arxiv_metadata("2401.00001")

    assert metadata is not None
    assert metadata.title == "Primary Host"
    assert FakeClient.calls == [(export_url, ["2401.00001"], 1, 1)]
