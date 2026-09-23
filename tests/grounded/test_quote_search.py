"""Search can rank however it likes; it can only ever return verbatim, cited sentences."""

from grounded import quote_search, sources
from grounded.quote_search import Passage


def test_local_search_returns_only_verbatim_located_quotes():
    result = quote_search.search("apply for disaster assistance deadline", top=5)
    assert result["engine"] == "local-bm25"
    assert result["results"]
    for hit in result["results"]:
        doc = sources.corpus()[hit["doc_id"]]
        assert doc.text[hit["start"] : hit["end"]] == hit["quote"]
        assert hit["url"].startswith("https://")


def test_a_search_engine_hit_that_is_not_in_the_source_is_dropped(monkeypatch):
    real = quote_search.passages()[0]

    class _Index:
        def search(self, query, top):
            return [
                real,
                Passage("fake-0", real.doc_id, 0, 40, "FEMA will pay every applicant $10,000 today."),
            ]

    monkeypatch.setattr(quote_search, "_azure_index", lambda: _Index())
    result = quote_search.search("payment", top=5)
    assert result["engine"] == "azure-ai-search"
    assert [hit["quote"] for hit in result["results"]] == [real.text]
    assert result["dropped_unverifiable"] == 1


def test_an_unreachable_search_service_falls_back_to_local(monkeypatch):
    class _Down:
        def search(self, query, top):
            raise ConnectionError("search service unreachable")

    monkeypatch.setattr(quote_search, "_azure_index", lambda: _Down())
    result = quote_search.search("appeal a decision", top=3)
    assert result["engine"] == "local-bm25"
    assert result["results"]


def test_the_endpoint_is_served_under_grounded():
    from fastapi.testclient import TestClient

    from api.main import app

    response = TestClient(app).get("/grounded/api/quotes/search", params={"q": "crisis counselor"})
    assert response.status_code == 200
    assert all("quote" in hit for hit in response.json()["results"])
