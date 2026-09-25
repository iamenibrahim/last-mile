from __future__ import annotations

import json
from copy import deepcopy
from datetime import date
from pathlib import Path

import pytest
from starlette.requests import Request

from api.main import _surge_for
from api.navigator import load_programs, navigate
from api.protocol import build_action_packet, verify_action_packet
from api.reliability import (
    MAX_SOURCE_EXCERPT_CHARS,
    SurgeController,
    assess_freshness,
    compile_accessibility,
    detect_packet_contradictions,
    detect_source_conflicts,
    diff_packet,
    evaluate_chaos,
    evidence_trace,
    offline_snapshot,
    validate_program_records,
)
from api.scenarios import replay_scenarios


ROOT = Path(__file__).resolve().parents[1]
PROFILE = {
    "location": "24370",
    "jurisdiction": "Smyth County",
    "urgency": "safe_now",
    "needs": ["housing", "documents"],
    "circumstances": ["displaced", "no_id"],
    "context_reviewed": True,
}


def test_every_program_stores_freshness_source_and_disaster_metadata():
    programs = json.loads((ROOT / "data" / "programs.json").read_text(encoding="utf-8"))
    assert validate_program_records(programs) == {
        "valid": True,
        "record_count": len(programs),
        "errors": [],
    }


def test_program_schema_accepts_null_expiration_and_reviewed_emergency_link():
    programs = json.loads((ROOT / "data" / "programs.json").read_text(encoding="utf-8"))
    emergency = next(program for program in programs if program["id"] == "emergency-911")
    assert emergency["expiration_date"] is None
    assert emergency["apply_url"] == "tel:911"
    assert validate_program_records([emergency])["valid"] is True


def test_program_schema_reports_precise_review_metadata_error():
    programs = json.loads((ROOT / "data" / "programs.json").read_text(encoding="utf-8"))
    malformed = dict(programs[0])
    malformed.pop("last_verified")
    malformed["expiration_date"] = "September 30"
    report = validate_program_records([malformed])
    assert report["valid"] is False
    assert {
        (error["field"], error["code"])
        for error in report["errors"]
    } == {("last_verified", "required"), ("expiration_date", "invalid_iso_date")}


def test_program_loader_fails_closed_when_review_metadata_is_omitted(tmp_path, monkeypatch):
    programs = json.loads((ROOT / "data" / "programs.json").read_text(encoding="utf-8"))
    programs[0].pop("expiration_date")
    catalog = tmp_path / "programs.json"
    catalog.write_text(json.dumps(programs), encoding="utf-8")
    monkeypatch.setattr("api.navigator.PROGRAMS_PATH", catalog)
    with pytest.raises(ValueError, match=r"record 0 field expiration_date: expiration_date is required"):
        load_programs()


def test_program_schema_rejects_duplicate_ids_and_unreviewed_destinations():
    programs = json.loads((ROOT / "data" / "programs.json").read_text(encoding="utf-8"))
    first = dict(programs[0])
    duplicate = dict(first)
    duplicate["source_url"] = "https://example.com/program"
    duplicate["apply_url"] = "tel:5551234"
    report = validate_program_records([first, duplicate])
    assert report["valid"] is False
    assert {(error["field"], error["code"]) for error in report["errors"]} == {
        ("id", "duplicate"),
        ("source_url", "unreviewed_domain"),
        ("apply_url", "unreviewed_tel_link"),
    }


def test_program_schema_rejects_non_https_and_invalid_review_interval():
    programs = json.loads((ROOT / "data" / "programs.json").read_text(encoding="utf-8"))
    malformed = dict(programs[1])
    malformed["apply_url"] = "http://211virginia.org/"
    malformed["review_interval_days"] = 0
    report = validate_program_records([malformed])
    assert {(error["field"], error["code"]) for error in report["errors"]} == {
        ("apply_url", "invalid_url"),
        ("review_interval_days", "invalid_value"),
    }


def test_recommendation_exposes_validated_freshness_metadata():
    recommendation = navigate({**PROFILE, "surge_mode": True})["recommendations"][0]
    assert {
        "status",
        "stale",
        "last_verified",
        "expiration_date",
        "review_interval_days",
        "reasons",
    } <= recommendation["source_freshness"].keys()


def test_freshness_checker_flags_old_and_expired_records():
    report = assess_freshness(
        {"last_verified": "2024-01-01", "expiration_date": "2024-02-01", "review_interval_days": 30},
        today=date(2026, 9, 24),
    )
    assert report["stale"]
    assert len(report["reasons"]) == 2


@pytest.mark.parametrize(
    "record,expected_stale,expected_code",
    [
        (
            {"last_verified": "2026-09-01", "expiration_date": None, "review_interval_days": 30},
            False,
            None,
        ),
        (
            {"last_verified": "2026-08-01", "expiration_date": None, "review_interval_days": 30},
            True,
            "review_overdue",
        ),
        (
            {"last_verified": "2026-09-01", "expiration_date": "2026-09-20", "review_interval_days": 30},
            True,
            "expired",
        ),
        (
            {"expiration_date": None, "review_interval_days": 30},
            True,
            "missing_last_verified",
        ),
        (
            {"last_verified": "09/01/2026", "expiration_date": None, "review_interval_days": 30},
            True,
            "invalid_last_verified",
        ),
        (
            {"last_verified": "2026-10-01", "expiration_date": None, "review_interval_days": 30},
            True,
            "future_last_verified",
        ),
    ],
)
def test_freshness_cases_use_an_injected_date(record, expected_stale, expected_code):
    report = assess_freshness(record, today=date(2026, 9, 30))
    assert report["stale"] is expected_stale
    assert report["status"] == ("stale" if expected_stale else "current")
    assert report["as_of"] == "2026-09-30"
    if expected_code:
        assert expected_code in report["reason_codes"]
        assert report["caveat"]
    else:
        assert report["reason_codes"] == []
        assert report["caveat"] is None


def test_missing_or_invalid_expiration_is_stale_but_null_is_non_expiring():
    base = {"last_verified": "2026-09-01", "review_interval_days": 30}
    assert assess_freshness({**base, "expiration_date": None}, today=date(2026, 9, 30))["stale"] is False
    missing = assess_freshness(base, today=date(2026, 9, 30))
    invalid = assess_freshness({**base, "expiration_date": "never"}, today=date(2026, 9, 30))
    assert missing["reason_codes"] == ["missing_expiration_date"]
    assert invalid["reason_codes"] == ["invalid_expiration_date"]


def test_future_review_date_is_stale_and_routes_recommendations_to_review(monkeypatch):
    programs = json.loads((ROOT / "data" / "programs.json").read_text(encoding="utf-8"))
    for program in programs:
        program["last_verified"] = "2026-10-01"
    monkeypatch.setattr("api.navigator.load_programs", lambda: programs)
    result = navigate({**PROFILE, "surge_mode": True}, today=date(2026, 9, 30))
    assert result["recommendations"]
    assert all(item["confidence"]["label"] == "Needs source review" for item in result["recommendations"])
    assert all(item["confidence"]["label"] != "Strong match" for item in result["recommendations"])
    assert result["handoff"]["recommended"] is True
    assert any("matched source needs review" in reason for reason in result["handoff"]["reasons"])


def test_recommendation_contains_complete_evidence_trace_and_graph():
    result = navigate({**PROFILE, "surge_mode": True})
    recommendation = result["recommendations"][0]
    assert set(recommendation["evidence"]) == {
        "schema_version",
        "rule",
        "source_record",
        "source_excerpt",
        "source_excerpt_truncated",
        "last_reviewed",
        "confidence",
        "caveat",
    }
    assert recommendation["evidence"]["schema_version"] == "recommendation-evidence-v1"
    assert len(recommendation["provenance"]["nodes"]) == 5


def test_every_recommendation_has_a_complete_trace_to_a_reviewed_catalog_record():
    programs = json.loads((ROOT / "data" / "programs.json").read_text(encoding="utf-8"))
    catalog = {program["id"]: program for program in programs}
    recommendations = navigate({**PROFILE, "surge_mode": True})["recommendations"]
    assert recommendations
    for recommendation in recommendations:
        evidence = recommendation["evidence"]
        source = evidence["source_record"]
        assert evidence["rule"].strip()
        assert 0 < len(evidence["source_excerpt"]) <= MAX_SOURCE_EXCERPT_CHARS
        assert evidence["last_reviewed"]
        assert evidence["confidence"]["label"]
        assert evidence["caveat"].strip()
        assert source["program_id"] in catalog
        assert source["source_url"] == catalog[source["program_id"]]["source_url"]


def test_evidence_trace_bounds_excerpt_and_fails_closed_when_required_data_is_missing():
    program = json.loads((ROOT / "data" / "programs.json").read_text(encoding="utf-8"))[0]
    long_program = {**program, "source_excerpt": "verified " * 100}
    trace = evidence_trace(long_program, ["shelter"], [], {"label": "Possible match", "value": 0.68})
    assert len(trace["source_excerpt"]) <= MAX_SOURCE_EXCERPT_CHARS
    assert trace["source_excerpt_truncated"] is True
    with pytest.raises(ValueError, match="source_excerpt"):
        evidence_trace({**program, "source_excerpt": ""}, [], [], {"label": "Possible match", "value": 0.68})


def test_foundry_explanation_cannot_replace_deterministic_rule_or_source_excerpt(monkeypatch):
    marker = "MODEL TEXT THAT IS NOT SOURCE EVIDENCE"
    monkeypatch.setattr("api.navigator._explain", lambda *args, **kwargs: (marker, "test model"))
    recommendation = navigate(PROFILE)["recommendations"][0]
    catalog = json.loads((ROOT / "data" / "programs.json").read_text(encoding="utf-8"))
    source = next(program for program in catalog if program["id"] == recommendation["id"])
    assert recommendation["why"] == marker
    assert marker not in recommendation["evidence"]["rule"]
    assert recommendation["evidence"]["source_excerpt"] == source["source_excerpt"]


def test_field_level_contradiction_detector_withholds_bad_channel():
    packet = build_action_packet(PROFILE)["packet"]
    packet["channels"]["voice"]["locked_facts"].remove("Smyth County")
    packet["channels"]["voice"]["script"] = packet["channels"]["voice"]["script"].replace(
        "Smyth County", "Washington County"
    )
    report = detect_packet_contradictions(packet)
    assert report["contradiction_detected"]
    assert report["action"] == "withhold_and_route_to_human"


@pytest.mark.parametrize(
    "old,new,field",
    [
        ("Smyth County", "Washington County", "jurisdiction"),
        ("DR-4831-VA", "DR-9999-VA", "disaster.id"),
        ("December 2, 2024", "December 20, 2024", "deadline.value"),
        ("800-621-3362", "800-555-0100", "escalation.contact_phone"),
    ],
)
def test_contradiction_detector_rejects_wrong_locked_value_even_when_lock_metadata_remains(old, new, field):
    packet = build_action_packet(PROFILE)["packet"]
    packet["channels"]["voice"]["script"] = packet["channels"]["voice"]["script"].replace(old, new)
    report = detect_packet_contradictions(packet)
    assert report["schema_version"] == "packet-contradictions-v2"
    assert any(item["channel"] == "voice" and item["field"] == field for item in report["contradictions"])


def test_every_compiled_channel_carries_the_structured_field_contract():
    packet = build_action_packet(PROFILE)["packet"]
    assert detect_packet_contradictions(packet)["passed"] is True
    for channel_name, channel in packet["channels"].items():
        rendered = json.dumps({key: value for key, value in channel.items() if key != "locked_facts"})
        assert "Smyth County" in rendered, channel_name
        assert "DR-4831-VA" in rendered, channel_name
        assert "December 2, 2024" in rendered, channel_name
        assert "800-621-3362" in rendered, channel_name
        assert packet["eligibility"]["notice"] in rendered, channel_name
        assert "historical" in rendered.casefold(), channel_name
        assert "passed" in rendered.casefold() or "closed" in rendered.casefold(), channel_name


def test_missing_or_unknown_action_source_is_rejected():
    missing = build_action_packet(PROFILE)["packet"]
    missing["actions"][0].pop("source_id")
    missing_report = detect_packet_contradictions(missing)
    assert {item["reason"] for item in missing_report["contradictions"] if item["field"] == "action.source_id"} == {"missing"}

    unknown = build_action_packet(PROFILE)["packet"]
    unknown["actions"][0]["source_id"] = "unreviewed-source"
    unknown_report = detect_packet_contradictions(unknown)
    assert {item["reason"] for item in unknown_report["contradictions"] if item["field"] == "action.source_id"} == {"unknown_source"}


def test_unsupported_eligibility_assertion_and_negation_change_are_rejected():
    packet = build_action_packet(PROFILE)["packet"]
    packet["channels"]["web"]["eligibility"] = "You will qualify for assistance."
    report = detect_packet_contradictions(packet)
    assert any(
        item["channel"] == "web"
        and item["field"] == "eligibility.claim"
        and item["reason"] == "unsupported_entitlement_assertion"
        for item in report["contradictions"]
    )


def test_eligibility_condition_absent_from_structured_packet_is_rejected():
    packet = build_action_packet(PROFILE)["packet"]
    packet["channels"]["web"]["eligibility"] += " Applicants must be homeowners."
    report = detect_packet_contradictions(packet)
    assert any(
        item["channel"] == "web"
        and item["field"] == "eligibility.condition"
        and item["reason"] == "unsupported_eligibility_condition"
        for item in report["contradictions"]
    )


def test_historical_current_status_inversion_is_rejected():
    packet = build_action_packet(PROFILE)["packet"]
    packet["channels"]["voice"]["script"] = packet["channels"]["voice"]["script"].replace(
        "Historical demonstration.", "The application is open."
    )
    report = detect_packet_contradictions(packet)
    assert any(
        item["channel"] == "voice"
        and item["field"] == "disaster.status"
        and item["reason"] == "historical_current_inversion"
        for item in report["contradictions"]
    )


def test_channel_only_omission_and_insertion_are_rejected():
    packet = build_action_packet(PROFILE)["packet"]
    packet["channels"]["web"]["deadline"] = "The application deadline has passed."
    packet["channels"]["offline"]["text"] += "\nAlso see disaster DR-9999-VA."
    report = detect_packet_contradictions(packet)
    findings = {(item["channel"], item["field"], item["reason"]) for item in report["contradictions"]}
    assert ("web", "deadline.value", "missing_from_rendered_output") in findings
    assert ("offline", "disaster.id", "unexpected_value") in findings


def test_extra_deadline_is_rejected_even_when_the_correct_deadline_remains():
    packet = build_action_packet(PROFILE)["packet"]
    packet["channels"]["offline"]["text"] += "\nThe application deadline was December 20, 2024."
    report = detect_packet_contradictions(packet)
    assert {
        "channel": "offline",
        "field": "deadline.value",
        "reason": "unexpected_value",
    } in report["contradictions"]


def test_contradictions_invalidate_a_rehashed_and_resigned_packet():
    from api import signing
    from api.protocol import _hash, _packet_message

    packet = build_action_packet(PROFILE)["packet"]
    packet["channels"]["voice"]["script"] = packet["channels"]["voice"]["script"].replace(
        "Smyth County", "Washington County"
    )
    packet["proof"]["channels_sha256"] = _hash(packet["channels"])
    packet["proof"].update(signing.sign(_packet_message(packet)))
    verified = verify_action_packet(packet)
    assert verified["signature_valid"] is True
    assert verified["channels_valid"] is True
    assert verified["field_consistency"]["contradiction_detected"] is True
    assert verified["valid"] is False


def test_contradiction_diagnostics_are_bounded_and_do_not_echo_values():
    packet = build_action_packet(PROFILE)["packet"]
    packet["channels"] = {f"channel-{index}": {} for index in range(100)}
    report = detect_packet_contradictions(packet)
    assert report["contradiction_count"] > len(report["contradictions"])
    assert len(report["contradictions"]) == 64
    assert report["diagnostics_truncated"] is True
    assert all(set(item) == {"channel", "field", "reason"} for item in report["contradictions"])


def test_chaos_dashboard_declares_safe_fallback_for_every_mode():
    modes = ["foundry_down", "translator_down", "maps_down", "stale_source", "bad_translation", "no_network"]
    result = evaluate_chaos(modes)
    assert len(result["outcomes"]) == 6
    assert all(item["safe"] and item["fallback"] for item in result["outcomes"])


def test_scenario_replay_passes_routing_escalation_locking_and_fallback():
    result = replay_scenarios()
    assert result["scenario_count"] >= 4
    assert result["failed"] == 0


def test_accessibility_profile_is_non_sensitive_and_compiles_channel_directives():
    result = compile_accessibility(["screen_reader", "voice_preferred", "relay_service", "unknown"])
    assert result["contains_sensitive_data"] is False
    assert result["preferred_channel"] == "voice"
    assert result["relay_contact"] == "711"
    assert "unknown" not in result["preferences"]


def test_handoff_packet_has_structured_handle_time_fields_without_sensitive_details():
    result = navigate({**PROFILE, "already_tried": ["called insurer"], "surge_mode": True})
    summary = result["handoff"]["summary"]
    assert summary["already_tried"] == ["called insurer"]
    assert summary["relevant_programs"]
    assert "unsafe_shelter" not in summary["circumstances"]


def test_source_conflicts_never_silently_choose_a_claim():
    report = detect_source_conflicts(
        [
            {"id": "a", "authoritative_claims": [{"field": "deadline", "value": "2026-10-01"}]},
            {"id": "b", "authoritative_claims": [{"field": "deadline", "value": "2026-10-02"}]},
        ]
    )
    assert report["conflict_detected"]
    assert report["action"] == "route_to_human_verification"


@pytest.mark.parametrize(
    "field,left,right,canonical_field",
    [
        ("deadline", "2026-10-01", "2026-10-02", "application_deadline"),
        ("phone", "800-555-0100", "800-555-0199", "contact_phone"),
        ("eligibility", "Must be a renter", "Homeowners only", "eligibility_condition"),
        ("status", "open", "closed", "program_status"),
    ],
)
def test_conflict_fixtures_preserve_both_exact_values_and_sources(field, left, right, canonical_field):
    report = detect_source_conflicts(
        [
            {"id": "source-a", "source_url": "https://www.fema.gov/a", "authoritative_claims": [{"field": field, "value": left}]},
            {"id": "source-b", "source_url": "https://www.fema.gov/b", "authoritative_claims": [{"field": field, "value": right}]},
        ]
    )
    assert report["conflict_detected"] is True
    conflict = report["conflicts"][0]
    assert conflict["field"] == canonical_field
    assert {claim["value"] for claim in conflict["claims"]} == {left, right}
    assert {claim["source_id"] for claim in conflict["claims"]} == {"source-a", "source-b"}


def test_identical_normalized_claims_are_not_conflicts_and_unsupported_prose_is_ignored():
    records = [
        {
            "id": "source-a",
            "authoritative_claims": [
                {"field": "phone", "value": "(800) 555-0100"},
                {"field": "free_text_summary", "value": "Applications are generally available"},
            ],
        },
        {
            "id": "source-b",
            "authoritative_claims": [
                {"field": "contact_phone", "value": "800-555-0100"},
                {"field": "free_text_summary", "value": "Applications may be available"},
            ],
        },
    ]
    assert detect_source_conflicts(records) == {
        "conflict_detected": False,
        "conflicts": [],
        "action": "continue",
    }


def test_conflicted_recommendations_lose_normal_confidence_and_route_to_human(monkeypatch):
    programs = json.loads((ROOT / "data" / "programs.json").read_text(encoding="utf-8"))
    for program, value in zip(programs[:2], ("open", "closed")):
        program["authoritative_claims"] = [{"field": "program_status", "value": value}]
        program["needs"] = ["housing"]
    monkeypatch.setattr("api.navigator.load_programs", lambda: programs[:2])
    result = navigate({**PROFILE, "surge_mode": True}, today=date(2026, 9, 25))
    assert result["source_conflicts"]["conflict_detected"] is True
    assert all(item["source_conflict"]["detected"] for item in result["recommendations"])
    assert all(item["confidence"]["label"] == "Source conflict — verify" for item in result["recommendations"])
    assert result["handoff"]["recommended"] is True
    assert result["handoff"]["level"] == "source_conflict"


def test_packet_signature_covers_source_conflict_result(monkeypatch):
    from api import protocol

    disaster = deepcopy(protocol._load_disaster())
    conflicting_source = deepcopy(disaster["sources"][1])
    conflicting_source["id"] = "fema-deadline-conflict"
    conflicting_source["authoritative_claims"][0]["value"] = "2024-12-03"
    disaster["sources"].append(conflicting_source)
    monkeypatch.setattr(protocol, "_load_disaster", lambda disaster_id="DR-4831-VA": disaster)
    packet = build_action_packet(PROFILE)["packet"]
    verified = verify_action_packet(packet)
    assert packet["source_conflicts"]["conflict_detected"] is True
    assert verified["signature_valid"] is True
    assert verified["valid"] is False
    packet["source_conflicts"]["action"] = "continue"
    assert verify_action_packet(packet)["signature_valid"] is False


def test_packet_diff_reports_changed_deadline_and_source_hashes():
    old = build_action_packet(PROFILE)["packet"]
    current = json.loads(json.dumps(old))
    current["deadlines"][0]["value"] = "2026-10-01"
    current["proof"]["source_hashes"] = {"new": "hash"}
    result = diff_packet(old, current)
    assert result["changed"]
    assert {item["field"] for item in result["changes"]} == {"deadline", "source_hashes"}


def test_offline_snapshot_embeds_packet_sources_and_verification():
    packet = build_action_packet(PROFILE)["packet"]
    verification = verify_action_packet(packet)
    snapshot = offline_snapshot(packet, verification)
    assert snapshot["format"] == "last-mile-offline-snapshot-v1"
    assert snapshot["packet"]["continuity"]["code"] == packet["continuity"]["code"]
    assert snapshot["verification_at_export"]["valid"]


def test_surge_controller_switches_to_graceful_degradation():
    controller = SurgeController(limit=1, window_seconds=60)
    assert controller.observe()["mode"] == "normal"
    result = controller.observe()
    assert result["mode"] == "surge"
    assert "deterministic matching retained" in result["degradation"]


def test_surge_context_survives_hosts_that_do_not_copy_request_state():
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    result = _surge_for(request)
    assert result["mode"] in {"normal", "surge"}
    assert "active" in result


def test_web_exposes_freshness_evidence_chaos_and_signed_snapshot_controls():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    assert 'id="run-chaos"' in html
    assert 'id="preference-profile"' in html
    assert 'id="download-snapshot"' in html
    assert "evidence-trace" in script
    assert "source_freshness" in script
