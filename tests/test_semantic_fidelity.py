from types import SimpleNamespace

import grounded.providers.base as providers
from api import verify


class _Embedder:
    """Stands in for Foundry: vectors chosen so the test controls the cosine."""

    semantic = True

    def __init__(self, vectors):
        self._vectors = vectors

    def embed(self, texts):
        return [self._vectors[text] for text in texts]


def _with_embedder(monkeypatch, vectors):
    monkeypatch.setattr(providers, "get_registry", lambda: SimpleNamespace(embedder=_Embedder(vectors)))


def test_foundry_embeddings_decide_when_configured(monkeypatch):
    _with_embedder(monkeypatch, {"Move to higher ground.": [1.0, 0.0], "Suba a un lugar alto.": [0.95, 0.05]})
    result = verify.semantic_fidelity("Move to higher ground.", "Suba a un lugar alto.", 0.1, translated=True)
    assert result["method"] == "Foundry embeddings cosine similarity"
    assert result["passed"] is True


def test_a_meaning_change_fails_even_with_high_provider_confidence(monkeypatch):
    _with_embedder(monkeypatch, {"Move to higher ground.": [1.0, 0.0], "Quédese en el sótano.": [0.1, 1.0]})
    result = verify.semantic_fidelity("Move to higher ground.", "Quédese en el sótano.", 0.99, translated=True)
    assert result["passed"] is False


def test_without_foundry_the_method_says_it_is_not_a_meaning_check():
    result = verify.semantic_fidelity("Move to higher ground.", "Suba a un lugar alto.", 0.96, translated=True)
    assert "not a meaning check" in result["method"]


def test_round_trip_allows_harmless_synonyms_but_keeps_a_floor():
    good = verify.semantic_fidelity(
        "Heavy rain is causing flash flooding.",
        "Heavy rains caused flash floods.",
        0.9,
        translated=True,
        round_trip=True,
    )
    bad = verify.semantic_fidelity(
        "Move to higher ground now.",
        "You have moved to a place.",
        0.9,
        translated=True,
        round_trip=True,
    )
    assert good["passed"] is True
    assert bad["passed"] is False


def test_round_trip_treats_do_not_and_dont_as_the_same_negation():
    result = verify.semantic_fidelity(
        "Do not drive across flooded roads.",
        "Don't drive across flooded roads.",
        0.9,
        translated=True,
        round_trip=True,
    )
    assert result["passed"] is True
