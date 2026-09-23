"""Brief section 3.1 stage 4: the abstain policy.

The properties worth pinning down are not "abstention sometimes happens" but:

  1. it is per segment, never per document
  2. an abstained segment still carries the source text, so abstention never
     costs instruction coverage - the warning stays on the page, only the
     translation is withheld
  3. every failure direction is towards abstention: a check that crashes, a
     provider that dies, a judge whose output will not parse
  4. the five corruption classes are each caught
  5. clean text is not abstained wholesale (the policy is useless if it
     refuses everything)
"""

from __future__ import annotations

import pytest

from grounded import entities as ent, transform, verify as vf
from grounded.ingest import load_cached
from grounded.providers.base import get_registry
from grounded_eval import corrupt as C


@pytest.fixture(scope="module")
def alert() -> dict:
    """A real alert with both a polygon and instruction text."""
    alerts = load_cached()
    if not alerts:
        pytest.skip("no cached alerts; run scripts/fetch_corpus.py")
    candidates = [
        f for f in alerts
        if (f["properties"].get("instruction") or "").strip()
        and (f["properties"].get("description") or "").strip()
    ]
    if not candidates:
        pytest.skip("no cached alert carries an instruction field")
    return max(candidates, key=lambda f: len(f["properties"]["instruction"]))


# ---------------------------------------------------------------------------
# 1 and 2: granularity, and that abstention does not lose the warning
# ---------------------------------------------------------------------------


def test_corruption_abstains_only_the_damaged_segment(alert):
    baseline = transform.transform_alert(alert, lang="en")
    locked = {s["id"]: s.get("entities", []) for s in baseline["segments"]}
    targets = C.eligible_segments("hallucinate_instruction", baseline["segments"])
    if not targets:
        pytest.skip("no instruction segment to corrupt")
    target = targets[0]

    fn, record = C.make_corruptor("hallucinate_instruction", target, locked)
    damaged = transform.transform_alert(alert, lang="en", corrupt_fn=fn)
    assert record["applied"]

    by_id = {s["id"]: s for s in damaged["segments"]}
    assert by_id[target]["status"] == "verbatim_abstained"

    # Everything else keeps whatever status it had on the clean run. One bad
    # sentence degrades one sentence; the document does not fail whole.
    clean_by_id = {s["id"]: s for s in baseline["segments"]}
    for sid, seg in by_id.items():
        if sid == target:
            continue
        assert seg["status"] == clean_by_id[sid]["status"], (
            f"corrupting {target} changed unrelated segment {sid}"
        )


def test_abstained_segment_shows_the_source_text_verbatim(alert):
    baseline = transform.transform_alert(alert, lang="en")
    locked = {s["id"]: s.get("entities", []) for s in baseline["segments"]}
    targets = C.eligible_segments("drop_instruction", baseline["segments"])
    if not targets:
        pytest.skip("no instruction segment to corrupt")

    fn, _ = C.make_corruptor("drop_instruction", targets[0], locked)
    damaged = transform.transform_alert(alert, lang="en", corrupt_fn=fn)
    seg = next(s for s in damaged["segments"] if s["id"] == targets[0])

    assert seg["status"] == "verbatim_abstained"
    assert seg["output_text"] == seg["source_text"], (
        "an abstained segment must fall back to the source text, not to silence"
    )
    assert seg["output_text"].strip(), "abstention must never produce an empty segment"


def test_abstention_does_not_reduce_document_instruction_coverage(alert):
    """The property that makes abstention safe rather than merely cautious."""
    baseline = transform.transform_alert(alert, lang="en")
    locked = {s["id"]: s.get("entities", []) for s in baseline["segments"]}
    targets = C.eligible_segments("drop_instruction", baseline["segments"])
    if not targets:
        pytest.skip("no instruction segment to corrupt")

    fn, _ = C.make_corruptor("drop_instruction", targets[0], locked)
    damaged = transform.transform_alert(alert, lang="en", corrupt_fn=fn)

    assert damaged["abstained_count"] >= 1
    assert damaged["document_coverage"]["passed"], (
        "every required action must still be present on the page after abstention"
    )


def test_a_whole_document_never_fails_on_one_bad_segment(alert):
    baseline = transform.transform_alert(alert, lang="en")
    locked = {s["id"]: s.get("entities", []) for s in baseline["segments"]}
    targets = C.eligible_segments("alter_number", baseline["segments"])
    if not targets:
        pytest.skip("no numeric segment to corrupt")

    fn, _ = C.make_corruptor("alter_number", targets[0], locked)
    damaged = transform.transform_alert(alert, lang="en", corrupt_fn=fn)
    assert damaged["abstained_count"] < damaged["segment_count"], (
        "one damaged segment must not abstain the entire document"
    )


# ---------------------------------------------------------------------------
# 3: fail closed
# ---------------------------------------------------------------------------


class ExplodingEmbedder:
    name = "exploding"
    semantic = True

    def embed(self, texts):
        raise RuntimeError("provider is down")


class ExplodingJudge:
    name = "exploding"
    llm_backed = True

    def entails(self, source, candidate):
        raise RuntimeError("provider is down")


class UnparseableJudge:
    """An LLM that returns prose where JSON was demanded."""

    name = "chatty"
    llm_backed = True

    def entails(self, source, candidate):
        raise ValueError("Sure! Here is my analysis: the rewrite looks great.")


def test_embedder_failure_abstains_rather_than_passes():
    result = vf.check_semantic_fidelity("Move to higher ground now.",
                                        "Move to higher ground now.",
                                        ExplodingEmbedder())
    assert not result.passed
    assert "abstaining" in result.detail


@pytest.mark.parametrize("judge", [ExplodingJudge(), UnparseableJudge()])
def test_judge_failure_abstains_rather_than_passes(judge):
    result = vf.check_grounding("Move to higher ground now.",
                                "Move to higher ground now.", judge)
    assert not result.passed


def test_empty_back_translation_abstains():
    registry = get_registry()
    result = vf.check_semantic_fidelity("Do not drive on flooded roads.", "",
                                        registry.embedder)
    assert not result.passed


def test_segment_of_pure_entities_is_not_falsely_abstained():
    """A URL-only segment has no prose to verify. Failing it would inflate the
    false-abstention rate with a bookkeeping artefact, not a real refusal."""
    registry = get_registry()
    locked = ent.lock("https://www.weather.gov/safety/flood", None)
    verdict = vf.verify_segment(
        segment_id="s1",
        source_en=locked.masked,
        masked_candidate=locked.masked,
        back_translated_en=locked.masked,
        locked=locked.entities,
        is_required_action=False,
        embedder=registry.embedder,
        judge=registry.judge,
        lang="en",
    )
    assert verdict.passed, [c.to_dict() for c in verdict.checks]


# ---------------------------------------------------------------------------
# 4: each corruption class is caught
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", C.CLASSES)
def test_each_corruption_class_is_caught(alert, cls):
    baseline = transform.transform_alert(alert, lang="en")
    locked = {s["id"]: s.get("entities", []) for s in baseline["segments"]}
    targets = C.eligible_segments(cls, baseline["segments"])
    if not targets:
        pytest.skip(f"this alert has no segment eligible for {cls}")

    caught = 0
    attempted = 0
    for target in targets[:3]:
        fn, record = C.make_corruptor(cls, target, locked)
        damaged = transform.transform_alert(alert, lang="en", corrupt_fn=fn)
        if not record["applied"]:
            continue
        attempted += 1
        seg = next(s for s in damaged["segments"] if s["id"] == target)
        if seg["status"] == "verbatim_abstained":
            caught += 1
    if not attempted:
        pytest.skip(f"{cls} could not be applied to this alert")
    assert caught == attempted, f"{cls}: caught {caught} of {attempted}"


def test_lost_negation_is_diagnosed_as_a_lost_instruction():
    """The reason shown to a reader should name the actual failure. "Do not
    cross" becoming "cross" is an instruction failure, not generic drift."""
    result = vf.check_instruction_coverage(
        "Do not drive on flooded roads.",
        "Drive on flooded roads.",
        is_required_action=True,
    )
    assert not result.passed
    assert "negation" in result.detail.lower()


def test_invented_negation_is_caught():
    result = vf.check_instruction_coverage(
        "Drive with care on wet roads.",
        "Do not drive on wet roads.",
        is_required_action=True,
    )
    assert not result.passed


# ---------------------------------------------------------------------------
# 5: the policy is not vacuous
# ---------------------------------------------------------------------------


def test_clean_english_render_is_mostly_not_abstained(alert):
    """A refuser that refuses everything is not a safety feature."""
    result = transform.transform_alert(alert, lang="en")
    ratio = result["abstained_count"] / max(1, result["segment_count"])
    assert ratio < 0.5, (
        f"{result['abstained_count']}/{result['segment_count']} segments abstained on "
        f"clean text; the thresholds are too tight to be useful"
    )


def test_half_translated_output_is_caught():
    """The failure that motivated the fifth check: an engine that returns the
    English unchanged scores *high* on back-translation fidelity, because the
    round trip is the identity."""
    source = "Flooding is expected near the river tonight."
    result = vf.check_translation_completeness(source, source, lang="es")
    assert not result.passed
    assert "survive verbatim" in result.detail


def test_translation_completeness_is_not_applied_to_english():
    result = vf.check_translation_completeness("Move now.", "Move now.", lang="en")
    assert result.passed


def test_alert_without_instruction_produces_no_actions():
    """Brief section 3.3 INVARIANT: never infer an action."""
    feature = {
        "properties": {
            "id": "test",
            "event": "Flood Advisory",
            "headline": "Flood Advisory in effect",
            "description": "Minor flooding is occurring in low lying areas.",
            "instruction": None,
            "areaDesc": "Smyth, VA",
        }
    }
    result = transform.transform_alert(feature, lang="en")
    assert result["no_instructions_in_source"] is True
    assert result["steps"] == []
    assert "does not infer" in result["instruction_note"]
