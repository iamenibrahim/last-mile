"""The Foundry transport: caching, retries, and what it admits to the caller."""

from types import SimpleNamespace

import httpx
import pytest

from api.providers import azure_foundry


def _reply(payload: dict, status: int = 200, headers: dict | None = None) -> httpx.Response:
    request = httpx.Request("POST", "https://example.invalid/openai/v1/chat/completions")
    if status != 200:
        return httpx.Response(status, headers=headers or {}, json={}, request=request)
    body = {"choices": [{"message": {"content": __import__("json").dumps(payload)}}]}
    return httpx.Response(status, json=body, request=request)


class _Transport:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self._responses = list(responses)
        self.calls = 0

    def post(self, *_args, **_kwargs) -> httpx.Response:
        self.calls += 1
        return self._responses.pop(0)


@pytest.fixture(autouse=True)
def _foundry(monkeypatch):
    monkeypatch.setattr(
        azure_foundry,
        "settings",
        SimpleNamespace(
            foundry_endpoint="https://example.invalid",
            foundry_api_key="test-key",
            foundry_model="last-mile-gpt",
        ),
    )
    monkeypatch.setattr(azure_foundry.time, "sleep", lambda _seconds: None)
    azure_foundry.cache_clear()
    yield
    azure_foundry.cache_clear()


def test_an_identical_request_is_served_from_cache_and_says_so(monkeypatch):
    transport = _Transport([_reply({"text": "Leave now."})])
    monkeypatch.setattr(azure_foundry, "_client", lambda: transport)

    first_text, first_meta = azure_foundry.simplify("Evacuate immediately.")
    second_text, second_meta = azure_foundry.simplify("Evacuate immediately.")

    assert first_text == second_text == "Leave now."
    assert transport.calls == 1, "the second call must not reach the provider"
    assert first_meta["cached"] is False
    assert second_meta["cached"] is True


def test_a_different_segment_is_not_served_from_another_segments_cache(monkeypatch):
    transport = _Transport([_reply({"text": "Leave now."}), _reply({"text": "Stay inside."})])
    monkeypatch.setattr(azure_foundry, "_client", lambda: transport)

    assert azure_foundry.simplify("Evacuate immediately.")[0] == "Leave now."
    assert azure_foundry.simplify("Shelter in place.")[0] == "Stay inside."
    assert transport.calls == 2


def test_a_throttled_request_is_retried_rather_than_dropped_to_fallback(monkeypatch):
    transport = _Transport(
        [
            _reply({}, status=429, headers={"Retry-After": "1"}),
            _reply({"text": "Leave now."}),
        ]
    )
    monkeypatch.setattr(azure_foundry, "_client", lambda: transport)

    text, meta = azure_foundry.simplify("Evacuate immediately.")

    assert text == "Leave now."
    assert transport.calls == 2
    assert meta["engine"] == "microsoft-foundry"


def test_a_persistent_failure_still_raises_so_the_caller_can_fall_back(monkeypatch):
    transport = _Transport([_reply({}, status=503) for _ in range(azure_foundry.MAX_ATTEMPTS)])
    monkeypatch.setattr(azure_foundry, "_client", lambda: transport)

    with pytest.raises(httpx.HTTPStatusError):
        azure_foundry.simplify("Evacuate immediately.")
    assert transport.calls == azure_foundry.MAX_ATTEMPTS


def test_the_judge_verdict_is_cached_separately_from_the_transformation(monkeypatch):
    transport = _Transport(
        [
            _reply({"text": "Leave now."}),
            _reply({"entailed": True, "reason": "supported"}),
        ]
    )
    monkeypatch.setattr(azure_foundry, "_client", lambda: transport)

    azure_foundry.simplify("Evacuate immediately.")
    verdict = azure_foundry.judge_entailment("Evacuate immediately.", "Leave now.")

    assert verdict["passed"] is True
    assert verdict["cached"] is False
    assert azure_foundry.judge_entailment("Evacuate immediately.", "Leave now.")["cached"] is True
    assert transport.calls == 2


def test_the_cache_is_bounded(monkeypatch):
    transport = _Transport(
        [_reply({"text": f"line {i}"}) for i in range(azure_foundry.CACHE_LIMIT + 5)]
    )
    monkeypatch.setattr(azure_foundry, "_client", lambda: transport)

    for i in range(azure_foundry.CACHE_LIMIT + 5):
        azure_foundry.simplify(f"Segment {i}.")

    assert len(azure_foundry._CACHE) == azure_foundry.CACHE_LIMIT


def test_the_answer_is_found_when_the_deployment_wraps_or_renames_the_key():
    assert azure_foundry._only_text({"text": "Leave now."}) == "Leave now."
    assert (
        azure_foundry._only_text({"task": "x", "response_schema": {"text": "Leave now."}})
        == "Leave now."
    )
    assert azure_foundry._only_text({"advice": "Leave now."}) == "Leave now."


def test_an_ambiguous_response_is_refused_rather_than_guessed():
    with pytest.raises(KeyError):
        azure_foundry._only_text({"task": "Rewrite this.", "advice": "Leave now."})
    with pytest.raises(KeyError):
        azure_foundry._only_text({})
