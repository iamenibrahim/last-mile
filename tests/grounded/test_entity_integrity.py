"""The guarantee in brief section 3.1: locked entities survive verbatim.

The brief says "write the test that proves it", so these tests are written to
be adversarial rather than confirmatory. A test that only runs the happy path
proves nothing about a safety property.

What is actually being proven, precisely: entity preservation is *structural*.
The transformation stage never receives the entity text - it receives a
sentinel - so a paraphrase of a road number is not unlikely, it is
unrepresentable. The tests below establish that in three parts:

  1. locking removes every must-survive span from the text a model would see
  2. the round trip restores the original exactly
  3. any tampering with a sentinel is detected, in every way it can be tampered
"""

from __future__ import annotations

import re

import pytest

from grounded import entities as ent
from grounded.ingest import load_cached

REAL = """At 533 PM EDT, Doppler radar indicated heavy rain due to thunderstorms.
Between 0.5 and 1.5 inches of rain have fallen. Do not drive on VA-91 or US-11
between Exit 17 and Exit 22. Water is 3.5 feet deep near Middle Fork Holston
River. Call 540-555-0134 or 1...8 6 6...2 1 5...4 3 2 4 for help. Shelter is
open at 110 Main Street. More at https://www.weather.gov/safety/flood by
830 PM EDT Monday."""


@pytest.fixture(scope="module")
def gazetteer() -> ent.Gazetteer:
    g = ent.Gazetteer.load()
    g.add_from_area_desc("Smyth, VA; Tazewell, VA; Saltville; Chilhowie")
    return g


# ---------------------------------------------------------------------------
# 1. Locking removes the dangerous spans from what the model sees
# ---------------------------------------------------------------------------


def _leaked(result: ent.LockResult) -> list[ent.Entity]:
    """Entities whose surface form is still visible outside a sentinel.

    Two traps this avoids, both of which produce false leaks:

      * sentinels must be stripped first, because "[[E2]]" literally contains
        the digit 2, so a one-character numeric entity reads as a leak;
      * the match must respect word boundaries, because the entity "Lake" is a
        substring of the untouched word "Lakes" in "Village of Salem Lakes" -
        a different word, not an unlocked occurrence.
    """
    carrier = ent.SENTINEL_RE.sub(" ", result.masked)
    leaked = []
    for e in result.entities:
        pattern = re.escape(e.text)
        if e.text[:1].isalnum():
            pattern = r"(?<![\w'])" + pattern
        if e.text[-1:].isalnum():
            pattern = pattern + r"(?![\w'])"
        if re.search(pattern, carrier):
            leaked.append(e)
    return leaked


def test_masked_text_contains_no_locked_surface_form(gazetteer):
    """The core claim. Whatever the model does, it cannot damage what it never saw."""
    result = ent.lock(REAL, gazetteer)
    leaked = _leaked(result)
    assert not leaked, (
        "still visible to the model in the masked text: "
        + str([(e.kind, e.text) for e in leaked])
    )


@pytest.mark.parametrize(
    "surface,kind",
    [
        ("VA-91", "road"),
        ("US-11", "road"),
        ("Exit 17", "road"),
        ("3.5 feet", "measurement"),
        ("0.5", "number"),
        ("540-555-0134", "phone"),
        ("110 Main Street", "address"),
        ("https://www.weather.gov/safety/flood", "url"),
        ("Middle Fork Holston River", "waterway"),
        ("533 PM EDT", "time"),
    ],
)
def test_specific_entity_kinds_are_locked(gazetteer, surface, kind):
    result = ent.lock(REAL, gazetteer)
    # NWS hard-wraps, so an entity can legitimately span a line break and keep
    # the newline in its surface form. Compare on normalised whitespace.
    found = [
        e for e in result.entities
        if re.sub(r"\s+", " ", e.text).strip().rstrip(".") == surface
    ]
    assert found, f"{surface!r} was not locked at all; kinds present: " + str(
        sorted({e.kind for e in result.entities})
    )
    assert found[0].kind == kind, f"{surface!r} locked as {found[0].kind}, expected {kind}"


def test_nws_spoken_digit_phone_is_locked(gazetteer):
    """NWS writes hotline numbers as spoken digit groups for text-to-speech.

    A generic phone regex misses this and the digits then travel through the
    model unprotected - which is how a reporting hotline becomes a wrong number.
    """
    result = ent.lock(REAL, gazetteer)
    spoken = [e for e in result.entities if e.kind == "phone_spoken"]
    assert spoken, "the NWS spoken-digit phone format was not locked"
    assert "8 6 6" in spoken[0].text


def test_every_occurrence_gets_its_own_sentinel():
    """Sharing a sentinel between two occurrences silently breaks the
    'exactly once' integrity check, so each occurrence must be distinct."""
    text = "Water over I-81 and more water over I-81 again."
    result = ent.lock(text, None)
    roads = [e for e in result.entities if e.kind == "road"]
    assert len(roads) == 2
    assert roads[0].sentinel != roads[1].sentinel
    assert result.masked.count(roads[0].sentinel) == 1
    assert result.masked.count(roads[1].sentinel) == 1


def test_longer_match_wins_over_bare_number():
    """US-58 must lock as one road, not shatter into a number."""
    result = ent.lock("Flooding on US-58 near mile 3.", None)
    kinds = {e.text: e.kind for e in result.entities}
    assert "US-58" in kinds and kinds["US-58"] == "road"
    assert "58" not in kinds


# ---------------------------------------------------------------------------
# 2. Round trip
# ---------------------------------------------------------------------------


def test_round_trip_is_byte_identical(gazetteer):
    result = ent.lock(REAL, gazetteer)
    restored, report = ent.unlock(result.masked, result.entities)
    assert report.passed, report.reason()
    assert restored == REAL


def test_round_trip_survives_reordering(gazetteer):
    """Translation legitimately moves sentinels around. Order is not the check;
    presence exactly once is."""
    result = ent.lock("Water is 3.5 feet deep on I-81.", gazetteer)
    sentinels = re.findall(r"\[\[E\d+\]\]", result.masked)
    assert len(sentinels) >= 2
    reordered = " ".join(reversed(sentinels))
    report = ent.check_integrity(reordered, result.entities)
    assert report.passed, f"reordering should be allowed, got: {report.reason()}"


def test_unit_localisation_keeps_the_numeral_locked():
    """Translating the unit word is allowed; touching the numeral is not."""
    result = ent.lock("Water is 3.5 feet deep.", None)
    restored, report = ent.unlock(result.masked, result.entities, unit_lang="es")
    assert report.passed, report.reason()
    assert "3.5" in restored, "the numeral must survive unit localisation"
    assert "pies" in restored, "the unit word should be localised"


@pytest.mark.parametrize("lang", ["es", "tl", "ar", "prs"])
def test_unit_localisation_never_drops_the_number(lang):
    result = ent.lock("Between 0.5 and 1.5 inches of rain have fallen over 2 miles.", None)
    restored, report = ent.unlock(result.masked, result.entities, unit_lang=lang)
    assert report.passed, report.reason()
    for numeral in ("0.5", "1.5", "2"):
        assert numeral in restored


# ---------------------------------------------------------------------------
# 3. Tampering is always detected
# ---------------------------------------------------------------------------


def test_dropped_sentinel_is_detected(gazetteer):
    result = ent.lock(REAL, gazetteer)
    victim = result.entities[3]
    report = ent.check_integrity(result.masked.replace(victim.sentinel, ""), result.entities)
    assert not report.passed
    assert victim.sentinel in report.missing


def test_duplicated_sentinel_is_detected(gazetteer):
    result = ent.lock(REAL, gazetteer)
    victim = result.entities[2]
    tampered = result.masked.replace(victim.sentinel, victim.sentinel + " " + victim.sentinel, 1)
    report = ent.check_integrity(tampered, result.entities)
    assert not report.passed
    assert victim.sentinel in report.duplicated


def test_altered_sentinel_is_detected(gazetteer):
    """Renumbering a sentinel shows up as one missing and one unexpected."""
    result = ent.lock(REAL, gazetteer)
    victim = result.entities[1]
    report = ent.check_integrity(
        result.masked.replace(victim.sentinel, "[[E999]]", 1), result.entities
    )
    assert not report.passed
    assert victim.sentinel in report.missing
    assert "[[E999]]" in report.unexpected


@pytest.mark.parametrize("mangled", ["[ [E2] ]", "[[ E2 ]]", "[[E2]", "[E2]]"])
def test_mangled_sentinel_debris_is_detected(mangled):
    """Translators do mangle bracket markup. Debris must not pass silently."""
    result = ent.lock("Water over I-81 is 3 feet deep.", None)
    victim = next(e for e in result.entities if e.sentinel == "[[E2]]")
    report = ent.check_integrity(result.masked.replace(victim.sentinel, mangled), result.entities)
    assert not report.passed, f"{mangled!r} was accepted as intact"


def test_substituting_a_plausible_wrong_value_is_detected():
    """The headline failure: US-58 rendered as US-85.

    This is what entity locking exists to make impossible. The substituted text
    is perfectly well-formed - only the missing sentinel gives it away.
    """
    result = ent.lock("Do not cross US-58 tonight.", None)
    victim = next(e for e in result.entities if e.text == "US-58")
    report = ent.check_integrity(result.masked.replace(victim.sentinel, "US-85"), result.entities)
    assert not report.passed
    assert victim.sentinel in report.missing


def test_numeral_vanishing_after_restore_is_detected():
    """Belt and braces: even if sentinels look fine, a numeral that is not in
    the final string fails the check."""
    result = ent.lock("Water is 3.5 feet deep.", None)
    victim = next(e for e in result.entities if e.numeric_core == "3.5")
    victim.text = "several feet"
    victim.unit = None
    restored, report = ent.unlock(result.masked, result.entities)
    assert not report.passed
    assert victim.id in report.numeric_dropped


# ---------------------------------------------------------------------------
# 4. Against the real corpus
# ---------------------------------------------------------------------------


def test_round_trip_holds_across_the_whole_cached_corpus(gazetteer):
    """The claim is only worth reporting if it holds on real NWS text."""
    alerts = load_cached()
    if not alerts:
        pytest.skip("no cached alerts; run scripts/fetch_corpus.py")

    checked = 0
    for feature in alerts:
        props = feature["properties"]
        local = ent.Gazetteer.load()
        local.add_from_area_desc(props.get("areaDesc") or "")
        for field in ("headline", "description", "instruction"):
            text = props.get(field)
            if not text:
                continue
            result = ent.lock(text, local)
            restored, report = ent.unlock(result.masked, result.entities)
            assert report.passed, f"{field} of {props.get('id')}: {report.reason()}"
            assert restored == text, f"{field} of {props.get('id')} did not round trip"
            leaked = _leaked(result)
            assert not leaked, (
                f"{field} of {props.get('id')} leaked: "
                + str([(e.kind, e.text) for e in leaked])
            )
            checked += 1
    assert checked > 20, f"only {checked} fields exercised; corpus too small to be meaningful"
