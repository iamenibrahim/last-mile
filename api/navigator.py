from __future__ import annotations

import json
import re
import secrets
from datetime import date, datetime, timezone
from pathlib import Path

from .config import settings
from .reliability import (
    assert_valid_program_records,
    assess_freshness,
    compile_accessibility,
    detect_source_conflicts,
    evidence_trace,
    provenance_graph,
)


ROOT = Path(__file__).resolve().parents[1]
PROGRAMS_PATH = ROOT / "data" / "programs.json"


def load_programs() -> list[dict]:
    records = json.loads(PROGRAMS_PATH.read_text(encoding="utf-8"))
    return assert_valid_program_records(records)


def _confidence(score: int, missing: list[str]) -> dict:
    if score >= 7 and not missing:
        return {"label": "Strong match", "value": 0.9}
    if score >= 4:
        return {"label": "Possible match", "value": 0.68}
    return {"label": "Worth checking", "value": 0.48}


def _handoff_location(location: str) -> str:
    if re.fullmatch(r"\s*-?\d{1,2}(?:\.\d+)?\s*,\s*-?\d{1,3}(?:\.\d+)?\s*", location):
        return "Device location used; exact coordinates excluded"
    if re.search(r"\d", location) and not re.fullmatch(r"\s*\d{5}\s*", location):
        return "Virginia location; exact address excluded"
    return location


def _explain(program: dict, matched_needs: list[str], *, deterministic_only: bool = False) -> tuple[str, str]:
    fallback = program["why_template"].format(needs=", ".join(matched_needs) or "your situation")
    if deterministic_only or not settings.foundry_enabled:
        return fallback, "rules + reviewed source copy"
    try:
        from .providers.azure_foundry import explain_program

        return explain_program(program, matched_needs), "Microsoft Foundry grounded explanation"
    except Exception:
        return fallback, "rules + reviewed source copy (Foundry fallback)"


def navigate(profile: dict, *, today: date | None = None) -> dict:
    needs = set(profile.get("needs", []))
    circumstances = set(profile.get("circumstances", []))
    urgency = profile.get("urgency", "safe_now")
    location = (profile.get("location") or "Virginia").strip()
    surge_mode = bool(profile.get("surge_mode"))
    accessibility = compile_accessibility(profile.get("accessibility_preferences"))
    programs = load_programs()
    conflict_report = detect_source_conflicts(programs)
    results: list[dict] = []

    for program in programs:
        matched_needs = sorted(needs & set(program.get("needs", [])))
        matched_circumstances = sorted(circumstances & set(program.get("circumstances", [])))
        urgent_match = bool(program.get("urgent") and urgency in {"danger_now", "tonight"})
        if not matched_needs and not matched_circumstances and not urgent_match:
            continue
        score = len(matched_needs) * 3 + len(matched_circumstances) * 2 + program.get("base_priority", 0)
        if urgent_match:
            score += 8
        if score <= 0:
            continue
        missing = [field for field in program.get("questions", []) if not profile.get(field)]
        freshness = assess_freshness(program, today=today)
        confidence = _confidence(score, missing)
        if freshness["stale"]:
            confidence = {"label": "Needs source review", "value": min(confidence["value"], 0.35)}
        explanation, explanation_provider = _explain(
            program,
            matched_needs,
            deterministic_only=surge_mode or accessibility["low_bandwidth"],
        )
        trace = evidence_trace(program, matched_needs, matched_circumstances, confidence)
        result = {
            **program,
            "score": score,
            "confidence": confidence,
            "matched_needs": matched_needs,
            "matched_circumstances": matched_circumstances,
            "missing_information": missing,
            "why": explanation,
            "explanation_provider": explanation_provider,
            "source_freshness": freshness,
            "evidence": trace,
            "provenance": provenance_graph(program, trace),
            "eligibility_notice": "This is a screening result, not an eligibility decision. The agency makes the final decision.",
        }
        results.append(result)

    results.sort(key=lambda item: (-item["score"], item["name"]))
    life_safety = urgency == "danger_now"
    escalation_reasons: list[str] = []
    escalation_level = "none"
    if life_safety:
        escalation_reasons.append("You indicated immediate danger.")
        escalation_level = "urgent"
    if "unsafe_shelter" in circumstances:
        escalation_reasons.append("You indicated that your current shelter or living situation may not be safe.")
        escalation_level = "sensitive" if escalation_level != "urgent" else escalation_level
    if "fraud_concern" in circumstances:
        escalation_reasons.append("A person should review a suspected disaster scam or identity-theft concern.")
        escalation_level = "sensitive" if escalation_level not in {"urgent", "sensitive"} else escalation_level
    if "no_id" in circumstances:
        escalation_reasons.append("You may need document alternatives or identity-recovery help.")
    if "accessibility" in circumstances or "limited_english" in circumstances:
        escalation_reasons.append("A representative may help arrange language or accessibility support.")
    if "appeal_or_denied" in circumstances:
        escalation_reasons.append("A denial, appeal, or deadline can have high-impact consequences and should be reviewed by a person.")
        if escalation_level == "none":
            escalation_level = "high_impact"
    if needs.intersection({"medical", "funeral", "legal"}) and escalation_level == "none":
        escalation_reasons.append("This request may involve medical, bereavement, or legal consequences.")
        escalation_level = "high_impact"
    if "complex_case" in circumstances:
        escalation_reasons.append("Your situation does not fit the standard screening choices.")
        if escalation_level == "none":
            escalation_level = "ambiguous"
    if any(item["confidence"]["value"] < 0.6 for item in results[:3]):
        escalation_reasons.append("At least one high-priority match needs more information.")
        if escalation_level == "none":
            escalation_level = "ambiguous"
    if any(item["source_freshness"]["stale"] for item in results):
        escalation_reasons.append(
            "At least one matched source needs review; confirm time-sensitive details with the linked agency or a human navigator."
        )
        if escalation_level == "none":
            escalation_level = "source_review"
    if conflict_report["conflict_detected"]:
        escalation_reasons.append("Authoritative sources conflict; no source was silently preferred.")
        escalation_level = "source_conflict" if escalation_level == "none" else escalation_level
    if escalation_reasons and escalation_level == "none":
        escalation_level = "support"

    sensitive_handoff_flags = {
        "unsafe_shelter",
        "fraud_concern",
        "appeal_or_denied",
        "complex_case",
    }
    reference = f"LM-{secrets.token_hex(3).upper()}"
    handoff = {
        "recommended": bool(escalation_reasons),
        "level": escalation_level,
        "reasons": escalation_reasons,
        "reference": reference,
        "summary": {
            "location_shared": _handoff_location(location),
            "needs": sorted(needs),
            "circumstances": sorted(circumstances - sensitive_handoff_flags),
            "private_review_requested": bool(circumstances & sensitive_handoff_flags),
            "urgency": urgency,
            "top_programs": [item["name"] for item in results[:3]],
            "relevant_programs": [item["id"] for item in results[:3]],
            "already_tried": sorted(set(profile.get("already_tried", []))),
            "unresolved_ambiguity": sorted(
                {field for item in results[:3] for field in item.get("missing_information", [])}
            ),
            "accessibility_preferences": accessibility["preferences"],
        },
        "contacts": [
            {"label": "Emergency", "value": "911", "when": "Immediate danger or life-threatening emergency"},
            {"label": "Virginia 211", "value": "Dial 211", "when": "Local services, shelter, food, or a live navigator"},
            {"label": "Relay", "value": "Dial 711", "when": "Telecommunications relay support"},
        ]
        + (
            [{"label": "National Center for Disaster Fraud", "value": "866-720-5721", "when": "Suspected disaster-related fraud"}]
            if "fraud_concern" in circumstances
            else []
        ),
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "location": location,
        "recommendations": results[:8],
        "handoff": handoff,
        "source_conflicts": conflict_report,
        "accessibility": accessibility,
        "privacy": {
            "stored": False,
            "used": ["location you entered", "selected needs", "selected circumstances", "urgency", "optional access preferences", "optional already-tried steps"],
            "not_requested": [
                "Social Security number",
                "income amount",
                "immigration status",
                "bank information",
                "FEMA registration number",
                "document uploads",
            ],
            "message": "Your answers were used for this response and were not written to the application database.",
        },
        "empty_notice": None
        if results
        else "No confident program match was found. Virginia 211 can help a person review your situation.",
        "engine": "deterministic eligibility rules; Foundry explains but never decides",
        "operating_mode": {
            "mode": "surge" if surge_mode else "normal",
            "core_matching": "deterministic",
            "ai_explanation": "disabled" if surge_mode else "optional",
        },
    }
