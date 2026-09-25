from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .ingest import load_cached_alert
from .navigator import navigate
from .protocol import build_action_packet, verify_action_packet
from .transform import transform_alert


SCENARIOS_PATH = Path(__file__).resolve().parents[1] / "data" / "scenarios.json"


def replay_scenarios() -> dict[str, Any]:
    scenarios = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
    results = []
    for scenario in scenarios:
        profile = {**scenario["profile"], "surge_mode": True}
        navigation = navigate(profile)
        packet_result = build_action_packet(profile)
        transformed = transform_alert(
            load_cached_alert(),
            scenario.get("language", "es"),
            deterministic_only=True,
        )
        checks = {
            "routing": all(
                expected in {item["id"] for item in navigation["recommendations"]}
                for expected in scenario.get("expected_programs", [])
            ),
            "escalation": navigation["handoff"]["level"] == scenario.get(
                "expected_escalation", navigation["handoff"]["level"]
            ),
            "locked_facts": packet_result.get("status") != "complete"
            or verify_action_packet(packet_result["packet"])["locked_facts_present_across_compiled_state"],
            "language_safety": all(
                segment.get("status") in {"verified", "translated_verified", "simplified_verified", "verbatim_abstained"}
                for segment in transformed.get("segments", [])
            ) and all(
                segment.get("verification", {}).get("passed")
                or segment.get("status") == "verbatim_abstained"
                for segment in transformed.get("segments", [])
            ),
            "fallback": all(
                item["explanation_provider"].startswith("rules + reviewed")
                for item in navigation["recommendations"]
            ),
        }
        results.append(
            {
                "id": scenario["id"],
                "description": scenario["description"],
                "passed": all(checks.values()),
                "checks": checks,
            }
        )
    return {
        "scenario_count": len(results),
        "passed": sum(item["passed"] for item in results),
        "failed": sum(not item["passed"] for item in results),
        "results": results,
    }
