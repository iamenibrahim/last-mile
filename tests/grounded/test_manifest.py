"""Brief section 3.2: provenance-preserving transformation.

The manifest is only worth carrying if tampering with it fails. These tests
cover the four ways someone would try:

  1. edit the source alert after the fact
  2. edit the rendered text but keep the manifest
  3. edit the manifest but keep the signature
  4. pass off an adversarially corrupted render as a production artifact

They also pin the honesty boundary itself: a passing validation must never be
described as proof that NWS signed anything.
"""

from __future__ import annotations

import copy
import json

import pytest

from grounded import ingest, manifest as mf, transform
from grounded.providers.base import get_registry


@pytest.fixture(scope="module")
def feature() -> dict:
    alerts = ingest.load_cached()
    if not alerts:
        pytest.skip("no cached alerts; run scripts/fetch_corpus.py")
    return next(
        (f for f in alerts if (f["properties"].get("instruction") or "").strip()),
        alerts[0],
    )


@pytest.fixture(scope="module")
def render(feature) -> dict:
    return transform.transform_alert(feature, lang="en")


@pytest.fixture(scope="module")
def signed(render, feature) -> dict:
    return mf.build_signed(render, feature)


# ---------------------------------------------------------------------------
# Shape and canonicalisation
# ---------------------------------------------------------------------------


def test_manifest_carries_everything_the_brief_requires(signed):
    source = signed["source"]
    for key in ("url", "cap_id", "sha256", "sender", "sent", "fetched_at", "transport"):
        assert source.get(key), f"manifest source is missing {key}"
    assert signed["transform_chain"], "transform chain must not be empty"
    assert signed["segments"], "segment statuses must be recorded"
    assert signed["signature"]["value"]


def test_canonicalisation_is_stable_across_key_order():
    a = {"b": 1, "a": [3, {"z": 1, "y": 2}]}
    b = {"a": [3, {"y": 2, "z": 1}], "b": 1}
    assert mf.canonical_bytes(a) == mf.canonical_bytes(b)


def test_canonicalisation_survives_a_javascript_round_trip():
    """The bug this pins down: Python writes 7.0, JavaScript writes 7.

    A manifest is signed in Python, rendered in a browser, and posted back to
    /api/verify. Without ECMAScript number formatting the bytes differ and
    every genuine manifest reads as tampered - a verify button that can only
    ever say "INVALID".
    """
    original = {"target_grade": 7.0, "near_km": 5.0, "lat": -81.76, "n": 3}
    # What a browser hands back after JSON.parse -> JSON.stringify.
    after_js = json.loads('{"lat":-81.76,"n":3,"near_km":5,"target_grade":7}')
    assert mf.canonical_bytes(original) == mf.canonical_bytes(after_js)


def test_signature_survives_a_javascript_round_trip(signed):
    """End to end version of the above, over a real signed manifest."""
    as_js_would_send = json.loads(
        json.dumps(mf._js_numbers(signed), separators=(",", ":"))
    )
    report = mf.validate(as_js_would_send)
    assert report.valid or all(
        c.passed for c in report.checks if c.name == "signature_valid"
    ), [c.to_dict() for c in report.checks if not c.passed]


def test_source_hash_ignores_our_own_provenance_block(feature):
    """Annotating must not change the hash, or it could never be recomputed."""
    bare = {k: v for k, v in feature.items() if k != "_provenance"}
    assert ingest.sha256_of(bare) == ingest.sha256_of(feature)


def test_source_hash_is_reproducible_from_the_cached_file(feature):
    recorded = feature["_provenance"]["sha256"]
    assert ingest.sha256_of(feature) == recorded


def test_every_cached_alert_hash_verifies():
    alerts = ingest.load_cached()
    if not alerts:
        pytest.skip("no cached alerts")
    bad = [aid for aid, ok in ingest.verify_cached_hashes(alerts) if not ok]
    assert not bad, f"cached files whose hash no longer matches: {bad[:5]}"


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_untouched_manifest_validates(signed, feature, render):
    report = mf.validate(signed, feature=feature, rendered_segments=render["segments"])
    assert report.valid, [c.to_dict() for c in report.checks if not c.passed]


def test_validation_returns_the_source_side_by_side(signed, feature, render):
    report = mf.validate(signed, feature=feature, rendered_segments=render["segments"])
    assert report.source_text["description"] == feature["properties"]["description"]
    assert report.source_text["instruction"] == feature["properties"].get("instruction")


# ---------------------------------------------------------------------------
# Tampering
# ---------------------------------------------------------------------------


def test_edited_manifest_fails_signature(signed):
    tampered = copy.deepcopy(signed)
    # Flip to whichever status it is not, so the edit is a real mutation
    # regardless of how this particular render came out.
    current = tampered["segments"][0]["status"]
    tampered["segments"][0]["status"] = (
        "verbatim_abstained" if current == "translated_verified" else "translated_verified"
    )
    assert tampered["segments"][0]["status"] != current
    report = mf.validate(tampered)
    failed = {c.name for c in report.checks if not c.passed}
    assert "signature_valid" in failed
    assert not report.valid


def test_flipping_an_abstention_to_verified_is_detected(signed):
    """The attack that matters: make a withheld translation look approved."""
    tampered = copy.deepcopy(signed)
    victim = next(
        (s for s in tampered["segments"] if s["status"] == "verbatim_abstained"), None
    )
    if victim is None:
        pytest.skip("this render abstained on nothing")
    victim["status"] = "translated_verified"
    victim.pop("reason", None)
    report = mf.validate(tampered)
    assert not report.valid


def test_altered_source_is_detected(signed, feature, render):
    tampered_source = copy.deepcopy(feature)
    tampered_source["properties"]["instruction"] = "Evacuate immediately via Route 11."
    report = mf.validate(signed, feature=tampered_source,
                         rendered_segments=render["segments"])
    failed = {c.name for c in report.checks if not c.passed}
    assert "source_hash" in failed
    assert not report.valid


def test_altered_rendered_text_is_detected(signed, feature, render):
    tampered = copy.deepcopy(render["segments"])
    tampered[0]["output_text"] = "Evacuation is mandatory for your address."
    report = mf.validate(signed, feature=feature, rendered_segments=tampered)
    failed = {c.name for c in report.checks if not c.passed}
    assert "render_digest" in failed
    assert not report.valid


def test_render_digest_is_insensitive_to_timing_noise(signed, feature, render):
    """Re-rendering identical content must not invalidate the binding."""
    same = copy.deepcopy(render)
    same["elapsed_ms"] = 99999
    same["created_at"] = "2030-01-01T00:00:00Z"
    assert mf.render_digest(same) == mf.render_digest(render)


def test_manifest_from_another_key_is_not_silently_accepted(signed):
    tampered = copy.deepcopy(signed)
    tampered["signature"]["key_id"] = "someone-elses-key"
    report = mf.validate(tampered)
    assert not report.valid
    detail = " ".join(c.detail for c in report.checks if not c.passed)
    assert "cannot verify" in detail


def test_not_a_manifest_is_rejected_without_throwing():
    report = mf.validate({"hello": "world"})
    assert not report.valid
    assert report.checks[0].name == "well_formed"


# ---------------------------------------------------------------------------
# Adversarial renders are marked as such
# ---------------------------------------------------------------------------


def test_corrupted_render_is_flagged_as_non_production(feature):
    from grounded_eval import corrupt as C

    baseline = transform.transform_alert(feature, lang="en")
    locked = {s["id"]: s.get("entities", []) for s in baseline["segments"]}
    targets = C.eligible_segments("hallucinate_instruction", baseline["segments"])
    if not targets:
        pytest.skip("nothing to corrupt")

    fn, _ = C.make_corruptor("hallucinate_instruction", targets[0], locked)
    damaged = transform.transform_alert(feature, lang="en", corrupt_fn=fn)
    signed = mf.build_signed(damaged, feature)

    report = mf.validate(signed, feature=feature, rendered_segments=damaged["segments"])
    assert not report.valid, "a corruption-injected render must not validate as production"
    failed = {c.name for c in report.checks if not c.passed}
    assert "no_injected_corruption" in failed


# ---------------------------------------------------------------------------
# The honesty boundary
# ---------------------------------------------------------------------------


def test_manifest_states_the_trust_anchor_limit(signed):
    anchor = signed["source"]["trust_anchor"].lower()
    assert "not" in anchor and "signature" in anchor, (
        "the manifest must say in its own body that this is not a verified NWS signature"
    )


def test_validation_never_claims_nws_signed_anything(signed, feature, render):
    report = mf.validate(signed, feature=feature, rendered_segments=render["segments"])
    out = report.to_dict()
    assert report.valid
    proves = out["what_this_proves"].lower()
    assert "not the authenticity" in proves
    blob = json.dumps(out).lower()
    assert "c2pa" in blob, "future work should be named, not implied"


def test_transform_chain_records_which_engines_actually_ran(signed):
    registry = get_registry()
    engines = json.dumps(signed["transform_chain"])
    assert registry.simplifier.name in engines
    assert signed["providers"]["translator"] == registry.translator.name
