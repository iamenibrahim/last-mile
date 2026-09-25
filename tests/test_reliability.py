from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from api.navigator import navigate
from api.protocol import build_action_packet, verify_action_packet
from api.reliability import (
    SurgeController,
    assess_freshness,
    compile_accessibility,
    detect_packet_contradictions,
    detect_source_conflicts,
    diff_packet,
    evaluate_chaos,
    offline_snapshot,
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
    for program in programs:
        assert "last_verified" in program
        assert "expiration_date" in program
        assert program["source_url"]
        assert program["disaster_id"]


def test_freshness_checker_flags_old_and_expired_records():
    report = assess_freshness(
        {"last_verified": "2024-01-01", "expiration_date": "2024-02-01", "review_interval_days": 30},
        today=date(2026, 9, 24),
    )
    assert report["stale"]
    assert len(report["reasons"]) == 2


def test_recommendation_contains_complete_evidence_trace_and_graph():
    result = navigate({**PROFILE, "surge_mode": True})
    recommendation = result["recommendations"][0]
    assert set(recommendation["evidence"]) == {
        "rule", "source_record", "source_excerpt", "last_reviewed", "confidence", "caveat"
    }
    assert len(recommendation["provenance"]["nodes"]) == 5


def test_field_level_contradiction_detector_withholds_bad_channel():
    packet = build_action_packet(PROFILE)["packet"]
    packet["channels"]["voice"]["locked_facts"].remove("Smyth County")
    packet["channels"]["voice"]["script"] = packet["channels"]["voice"]["script"].replace(
        "Smyth County", "Washington County"
    )
    report = detect_packet_contradictions(packet)
    assert report["contradiction_detected"]
    assert report["action"] == "withhold_and_route_to_human"


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


def test_web_exposes_freshness_evidence_chaos_and_signed_snapshot_controls():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    assert 'id="run-chaos"' in html
    assert 'id="preference-profile"' in html
    assert 'id="download-snapshot"' in html
    assert "evidence-trace" in script
    assert "source_freshness" in script
