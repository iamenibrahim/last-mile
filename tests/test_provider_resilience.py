from types import SimpleNamespace

from api import transform
from api.ingest import load_cached_alert
from api.providers import azure_foundry, azure_translator


def _settings(**overrides):
    values = {
        "foundry_enabled": False,
        "translator_enabled": False,
        "content_safety_enabled": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_translator_outage_falls_back_without_losing_the_response(monkeypatch):
    monkeypatch.setattr(transform, "settings", _settings(translator_enabled=True))
    monkeypatch.setattr(
        azure_translator,
        "translate",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("simulated outage")),
    )

    result = transform.transform_alert(load_cached_alert(), language="es")

    assert result["segments"]
    assert {segment["provider"]["engine"] for segment in result["segments"]} == {
        "curated-demo-cache"
    }
    assert {segment["provider"]["fallback_reason"] for segment in result["segments"]} == {
        "TimeoutError"
    }


def test_foundry_outage_falls_back_without_losing_the_response(monkeypatch):
    monkeypatch.setattr(transform, "settings", _settings(foundry_enabled=True))
    monkeypatch.setattr(
        azure_foundry,
        "simplify",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("simulated outage")),
    )

    result = transform.transform_alert(load_cached_alert(), language="en")

    assert result["segments"]
    assert {segment["provider"]["engine"] for segment in result["segments"]} == {
        "deterministic-local"
    }
    assert {segment["provider"]["fallback_reason"] for segment in result["segments"]} == {
        "TimeoutError"
    }
