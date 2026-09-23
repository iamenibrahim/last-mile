"""Disaster Assistance Navigator: the properties that make it safe to put in
front of a flood survivor.

  1. Grounding     every sentence about a program is a verbatim quote that
                   slices out of a hash-verified authoritative document
  2. Data decides  Individual Assistance availability and deadlines come from
                   OpenFEMA fields, by FEMA's own documented rule
  3. The floor     escalation to a human is rule-based; a model can add to it
                   and never subtract from it
  4. Privacy       identifiers are removed before anything else sees the text,
                   and nothing typed is kept
  5. Ask, don't    an ambiguous location is returned as a choice, and a forged
     guess         choice is refused
  6. Refusal       damaging a FEMA fraud warning withholds it, never ships it
"""

from __future__ import annotations

import datetime as dt
import json

import pytest

from grounded import areas, escalation as esc, fema, manifest as mf, navigator, privacy, sources

UTC = dt.timezone.utc
HELENE_REPLAY = dt.datetime(2024, 10, 21, 15, 0, tzinfo=UTC)  # 20 days after DR-4831


@pytest.fixture(scope="module")
def smyth() -> dict:
    if not sources.corpus():
        pytest.skip("no source corpus; run scripts/fetch_fema.py and scripts/ingest_browser_sources.py")
    return navigator.navigate("Smyth", needs=list(navigator.NEEDS), now=HELENE_REPLAY)


# ---------------------------------------------------------------------------
# 1. Grounding
# ---------------------------------------------------------------------------


def test_every_catalog_quote_is_found_verbatim():
    raw = json.loads(sources.PROGRAMS_PATH.read_text(encoding="utf-8"))
    quotes = [c for p in raw["programs"] for c in p["claims"]]
    quotes += raw["status_notes"] + raw["fraud_warnings"]
    quotes += list(raw["rules"].values()) + list(raw["channels"].values())
    missing = [(q["doc"], q["quote"][:60]) for q in quotes if sources.locate(q["doc"], q["quote"]) is None]
    assert not missing, f"quotes not found verbatim in the cached source: {missing}"
    assert len(quotes) >= 60


def test_every_cited_segment_slices_to_its_exact_words(smyth):
    """The page-level form of the guarantee: a citation is an offset into a
    specific document, and that offset must still hold the quoted words."""
    corpus = sources.corpus()
    cited = [s for s in smyth["segments"] if (s.get("meta") or {}).get("citation")]
    assert len(cited) > 25
    for s in cited:
        c = s["meta"]["citation"]
        assert corpus[c["doc_id"]].text[c["start"]:c["end"]] == s["source_text"], s["id"]


def test_program_claims_are_never_uncited(smyth):
    by_id = {s["id"]: s for s in smyth["segments"]}
    for p in smyth["programs"]:
        for sid in p["claim_segments"]:
            assert by_id[sid]["meta"].get("citation"), f"{p['id']} claim {sid} has no citation"


def test_an_edited_source_document_is_refused(tmp_path, monkeypatch):
    """A cached document whose text no longer matches its recorded hash is
    dropped from the corpus rather than cited."""
    doc = sources.corpus()["fema-fraud"]
    tampered = json.loads((sources.SOURCES_DIR / "fema-fraud.json").read_text(encoding="utf-8"))
    tampered["text"] = tampered["text"].replace("never charge", "sometimes charge")
    (tmp_path / "fema-fraud.json").write_text(json.dumps(tampered), encoding="utf-8")
    monkeypatch.setattr(sources, "SOURCES_DIR", tmp_path)
    try:
        assert "fema-fraud" not in sources.corpus(reload=True)
    finally:
        monkeypatch.undo()
        sources.corpus(reload=True)
    assert doc.id in sources.corpus()


def test_browser_captures_reproduce_the_in_browser_hash():
    """fema.gov pages were hashed inside the browser at capture. Every file on
    disk must still reproduce that hash - otherwise a transcription slipped."""
    from scripts.grounded.ingest_browser_sources import BROWSER_DIR, parse

    files = sorted(BROWSER_DIR.glob("*.txt"))
    assert files, "no browser captures present"
    for path in files:
        meta, body = parse(path)
        assert sources.text_sha256(sources.normalise(body)) == meta["browser_sha256"], path.name


# ---------------------------------------------------------------------------
# 2. Data decides
# ---------------------------------------------------------------------------


def _row(ih: bool, ia: bool, last: str | None = "2024-12-02T00:00:00.000Z", dtype="DR") -> dict:
    return {"disasterNumber": 4831, "declarationType": dtype, "declarationTitle": "TEST",
            "declarationDate": "2024-10-01T00:00:00.000Z", "fipsStateCode": "51",
            "fipsCountyCode": "173", "designatedArea": "Smyth (County)",
            "ihProgramDeclared": ih, "iaProgramDeclared": ia, "paProgramDeclared": True,
            "lastIAFilingDate": last}


@pytest.mark.parametrize("ih,ia,expected", [(True, False, True), (False, True, True),
                                            (True, True, True), (False, False, False)])
def test_individual_assistance_is_ih_or_ia(ih, ia, expected):
    """FEMA's data dictionary: 'use both ihProgramDeclared and iaProgramDeclared'."""
    [status] = fema.declarations_for_county("51173", rows=[_row(ih, ia)])
    assert status.individual_assistance is expected


def test_deadline_windows_follow_the_regulation():
    """Open through the deadline day, then 60 late days (44 CFR 206.112(d)), then closed."""
    [s] = fema.declarations_for_county("51173", rows=[_row(True, False)])
    at = lambda y, m, d: dt.datetime(y, m, d, 12, tzinfo=UTC)  # noqa: E731
    assert fema.registration_window(s, at(2024, 10, 21))["days_left"] == 42
    assert fema.registration_window(s, at(2024, 12, 2))["state"] == "open"   # the last day itself
    late = fema.registration_window(s, at(2024, 12, 3))
    assert late["state"] == "late" and late["late_until"] == "2025-01-31"
    assert fema.registration_window(s, at(2025, 2, 1))["state"] == "closed"


def test_public_assistance_only_county_gets_no_individual_programs():
    [s] = fema.declarations_for_county("51173", rows=[_row(False, False, last=None)])
    a = {"primary": {"declaration": s, "window": fema.registration_window(s, HELENE_REPLAY)},
         "major_disaster_recent": True, "any_recent": True}
    assert navigator.availability("individual_assistance", a) == "unavailable"
    code, sentence = navigator.status_statement("Smyth County", a)
    assert code == "no_ia" and "does not include Individual Assistance" in sentence


def test_helene_replay_reads_the_real_declaration(smyth):
    primary = smyth["declarations"]["primary"]
    assert primary["declaration_string"] == "DR-4831-VA"
    assert primary["window"]["days_left"] == 42
    assert smyth["status_code"] == "ia_open"


def test_future_declarations_are_invisible_to_a_replay():
    r = navigator.navigate("Smyth", needs=["home_damaged"], now=HELENE_REPLAY)
    seen = [d["declaration_string"] for d in r["declarations"]["history"]]
    assert "EM-3631-VA" not in seen, "a 2026 declaration leaked into a 2024 replay"


def test_official_program_names_survive_plain_language(smyth):
    """Without locking, the simplifier turned this into 'Individual Help area'."""
    status = next(s for s in smyth["segments"] if s["role"] == "status")
    assert "Individual Assistance" in status["output_text"]
    assert "DR-4831-VA" in status["output_text"]


def test_vocabulary_of_record_is_not_simplified_away(smyth):
    rental = [s for s in smyth["segments"] if "rental assistance" in s["source_text"]]
    assert rental and all("rental assistance" in s["output_text"] for s in rental)


# ---------------------------------------------------------------------------
# 3. The escalation floor
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text,trigger,level", [
    ("my mother is trapped in the attic", "danger_now", "urgent"),
    ("water is rising in the house", "danger_now", "urgent"),
    ("I don't want to live anymore", "self_harm", "urgent"),
    ("mi hijo está atrapado", "danger_now", "urgent"),
    ("am I eligible if I have a green card", "immigration", "sensitive"),
    ("I never applied but got a FEMA letter", "identity_theft", "sensitive"),
    ("a man said FEMA wants a fee to apply", "fraud", "fraud"),
    ("my application was denied", "high_impact", "high_impact"),
])
def test_rules_catch_what_must_be_caught(text, trigger, level):
    found = {t.id: t.level for t in esc.rule_triggers(text)}
    assert found.get(trigger) == level, found


def test_a_model_cannot_lower_or_remove_an_escalation():
    floor = esc.rule_triggers("my father is trapped on the roof")
    # A model that calmly reports "no concern", and one that downgrades.
    calm = []
    downgrade = [esc.Trigger("danger_now", "none", "model says fine", [], source="model")]
    merged = esc.merge(floor, calm, downgrade)
    assert merged.level == "urgent"
    assert any(t.id == "danger_now" and t.level == "urgent" for t in merged.triggers)


def test_a_model_can_add_an_escalation():
    added = [esc.Trigger("abuse", "sensitive", "model noticed", ["legal_aid"], source="model")]
    assert esc.merge([], added).level == "sensitive"


def test_urgent_cases_put_a_human_first_even_without_a_location():
    r = navigator.navigate("", text="someone is trapped and injured", now=HELENE_REPLAY)
    assert r["escalation"]["level"] == "urgent"
    assert r["escalation"]["human_first"] is True
    assert any(c["label"] == "911" and c["verified"] for c in r["escalation"]["channels"])


def test_every_escalation_channel_is_a_verified_citation():
    raw = json.loads(sources.PROGRAMS_PATH.read_text(encoding="utf-8"))
    for cid in raw["channels"]:
        assert esc.resolve_channel(cid)["verified"], cid


def test_immigration_questions_surface_the_status_independent_help():
    r = navigator.navigate("Smyth", needs=["emotional_distress", "legal_help"],
                           text="I'm not a citizen, can my kids still get help?", now=HELENE_REPLAY)
    assert r["escalation"]["level"] in ("sensitive", "urgent")
    notes = [s for s in r["segments"] if s["role"] == "status_note"]
    assert notes and all(s["meta"]["emphasized"] for s in notes)
    assert any("minor child" in s["source_text"] for s in notes)
    flagged = {p["id"] for p in r["programs"] if p["status_independent"]}
    assert {"crisis-counseling", "legal-services"} <= flagged


# ---------------------------------------------------------------------------
# 4. Privacy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text,kind", [
    ("my ssn is 123-45-6789", "ssn"),
    ("registration 912345678", "nine_digit_id"),
    ("card 4111 1111 1111 1111", "card_number"),
    ("routing number 021000021", "bank_account"),
    ("born on 03/14/1961", "date_of_birth"),
    ("email me at a.person@example.com", "email"),
    ("call 540-555-0134", "phone"),
    ("I live at 217 Palmer Ave", "street_address"),
])
def test_identifiers_are_removed(text, kind):
    red = privacy.redact(text)
    assert kind in red.removed
    assert "removed" in red.text


def test_a_non_luhn_digit_run_is_not_mistaken_for_a_card():
    assert "card_number" not in privacy.redact("order 1234 5678 9012 3456").removed


def test_nothing_typed_survives_into_the_response():
    ssn, secret = "123-45-6789", "the blue house past the church"
    r = navigator.navigate("Smyth", needs=["home_damaged"], now=HELENE_REPLAY,
                           text=f"roof gone, SSN {ssn}, it's {secret}")
    blob = json.dumps(r)
    assert ssn not in blob
    assert secret not in blob
    assert "ssn" in r["privacy"]["removed"]


def test_escalation_still_works_on_redacted_text():
    r = navigator.navigate("Smyth", text="trapped in the attic, my SSN is 123-45-6789", now=HELENE_REPLAY)
    assert r["escalation"]["level"] == "urgent"


def test_the_assist_endpoint_stores_nothing():
    from fastapi.testclient import TestClient

    from grounded.main import app
    from grounded.store import get_store

    c = TestClient(app)
    r = c.post("/api/assist", json={"location": "Smyth", "needs": ["home_damaged"],
                                    "as_of": "2024-10-21T15:00:00Z"}).json()
    assert get_store().get_render(r["render_id"]) is None
    assert r["manifest"]["retained"]["county_fips"] == "51173"
    assert set(r["manifest"]["retained"]) >= {"county_fips", "needs", "escalation_level", "not_retained"}


# ---------------------------------------------------------------------------
# 5. Ask, don't guess
# ---------------------------------------------------------------------------


def test_a_zip_that_crosses_a_county_line_is_a_question():
    res = areas.resolve("24370")
    assert res.ambiguous and res.county_fips is None
    assert {c.county_name for c in res.candidates} == {"Smyth County", "Washington County"}


def test_a_valid_pick_resolves_and_a_forged_one_does_not():
    assert areas.resolve("24370", pick_fips="51191").county_name == "Washington County"
    forged = areas.resolve("24370", pick_fips="51059")  # Fairfax: not in this ZIP
    assert forged.county_fips is None and forged.ambiguous


def test_a_name_shared_by_a_county_and_a_city_is_a_question():
    res = areas.resolve("Roanoke")
    assert res.ambiguous
    assert {c.county_name for c in res.candidates} == {"Roanoke County", "Roanoke city"}


def test_independent_cities_resolve():
    assert areas.resolve("Galax").county_name == "Galax city"


# ---------------------------------------------------------------------------
# 6. Refusal, on the sentence a scammer would most like changed
# ---------------------------------------------------------------------------


def test_a_damaged_fraud_warning_is_withheld_not_shipped():
    from grounded_eval import corrupt as C

    base = navigator.navigate("Smyth", needs=["scam_concern"], now=HELENE_REPLAY)
    target = next(s for s in base["segments"] if s["role"] == "fraud" and "never charge" in s["source_text"])
    locked = {s["id"]: s.get("entities", []) for s in base["segments"]}
    fn, record = C.make_corruptor("drop_negation", target["id"], locked)
    damaged = navigator.navigate("Smyth", needs=["scam_concern"], now=HELENE_REPLAY, corrupt_fn=fn)
    seg = next(s for s in damaged["segments"] if s["id"] == target["id"])
    assert record["applied"]
    assert seg["status"] == "verbatim_abstained"
    assert "never charge" in seg["output_text"], "the reader must see FEMA's original words"


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def test_navigator_manifest_validates_and_tampering_fails(smyth):
    m = json.loads(json.dumps(mf.build_navigator_signed(smyth)))
    ok = mf.validate(m, rendered_segments=smyth["segments"])
    assert ok.valid, [c.to_dict() for c in ok.checks if not c.passed]

    edited = json.loads(json.dumps(smyth["segments"]))
    victim = next(s for s in edited if s["role"] == "fraud")
    victim["source_text"] = victim["source_text"].replace("never", "sometimes")
    victim["output_text"] = victim["output_text"].replace("never", "sometimes")
    bad = mf.validate(m, rendered_segments=edited)
    failed = {c.name for c in bad.checks if not c.passed}
    assert not bad.valid and {"citations_exact", "render_digest"} <= failed
