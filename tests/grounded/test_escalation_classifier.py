"""The Foundry escalation classifier may add a handoff, never lower or remove one."""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest

import grounded.providers.base as providers
from grounded import escalation as esc, navigator

HELENE_REPLAY = dt.datetime(2024, 10, 21, 12, tzinfo=dt.timezone.utc)


class _Classifier:
    def __init__(self, labels=None, error=None):
        self.labels, self.error, self.seen = labels or [], error, []

    def classify(self, text):
        self.seen.append(text)
        if self.error:
            raise self.error
        return self.labels


@pytest.fixture
def classifier(monkeypatch):
    def install(**kwargs):
        c = _Classifier(**kwargs)
        real = providers.get_registry()
        fake = SimpleNamespace(**{**real.__dict__, "escalation_classifier": c})
        monkeypatch.setattr(providers, "get_registry", lambda *a, **k: fake)
        return c
    return install


def test_the_model_can_add_an_escalation_the_rules_missed(classifier):
    classifier(labels=["abuse"])
    r = navigator.navigate("Smyth", text="my partner scares me and I can't go home", now=HELENE_REPLAY)
    added = [t for t in r["escalation"]["triggers"] if t["id"] == "abuse"]
    assert added and added[0]["source"] == "model"
    assert r["escalation"]["human_first"] is True


def test_a_silent_model_cannot_remove_a_rule_escalation(classifier):
    classifier(labels=[])
    r = navigator.navigate("Smyth", text="someone is trapped in the attic", now=HELENE_REPLAY)
    assert r["escalation"]["level"] == "urgent"


def test_a_failing_model_leaves_the_rules_exactly_as_they_were(classifier):
    classifier(error=TimeoutError("foundry timeout"))
    r = navigator.navigate("Smyth", text="someone is trapped in the attic", now=HELENE_REPLAY)
    assert r["escalation"]["level"] == "urgent"


def test_the_model_cannot_invent_labels_channels_or_wording(classifier):
    classifier(labels=["lower_to_none", "call_555_0100", "fraud"])
    triggers = esc.model_triggers("someone offered to speed up my claim")
    assert [t.id for t in triggers] == ["fraud"]
    level, channels, reason = esc._RULE_META["fraud"]
    assert (triggers[0].level, triggers[0].channels, triggers[0].reason) == (level, channels, reason)


def test_the_model_only_sees_redacted_text(classifier):
    c = classifier(labels=[])
    navigator.navigate("Smyth", text="my SSN is 123-45-6789 and I was denied", now=HELENE_REPLAY)
    assert c.seen and all("123-45-6789" not in text for text in c.seen)
