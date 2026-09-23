from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from pathlib import Path

from .config import settings


ROOT = Path(__file__).resolve().parents[1]
PROGRAMS_PATH = ROOT / "data" / "programs.json"


def _load_programs() -> list[dict]:
    return json.loads(PROGRAMS_PATH.read_text(encoding="utf-8"))


def _confidence(score: int, missing: list[str]) -> dict:
    if score >= 7 and not missing:
        return {"label": "Strong match", "value": 0.9}
    if score >= 4:
        return {"label": "Possible match", "value": 0.68}
    return {"label": "Worth checking", "value": 0.48}


def _explain(program: dict, matched_needs: list[str]) -> tuple[str, str]:
    fallback = program["why_template"].format(needs=", ".join(matched_needs) or "your situation")
    if not settings.foundry_enabled:
        return fallback, "rules + reviewed source copy"
    try:
        from .providers.azure_foundry import explain_program

        return explain_program(program, matched_needs), "Microsoft Foundry grounded explanation"
    except Exception:
        return fallback, "rules + reviewed source copy (Foundry fallback)"


def navigate(profile: dict) -> dict:
    needs = set(profile.get("needs", []))
    circumstances = set(profile.get("circumstances", []))
    urgency = profile.get("urgency", "safe_now")
    location = (profile.get("location") or "Virginia").strip()
    results: list[dict] = []

    for program in _load_programs():
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
        explanation, explanation_provider = _explain(program, matched_needs)
        result = {
            **program,
            "score": score,
            "confidence": _confidence(score, missing),
            "matched_needs": matched_needs,
            "matched_circumstances": matched_circumstances,
            "missing_information": missing,
            "why": explanation,
            "explanation_provider": explanation_provider,
            "eligibility_notice": "This is a screening result, not an eligibility decision. The agency makes the final decision.",
        }
        results.append(result)

    results.sort(key=lambda item: (-item["score"], item["name"]))
    life_safety = urgency == "danger_now"
    escalation_reasons: list[str] = []
    if life_safety:
        escalation_reasons.append("You indicated immediate danger.")
    if "no_id" in circumstances:
        escalation_reasons.append("You may need document alternatives or identity-recovery help.")
    if "accessibility" in circumstances or "limited_english" in circumstances:
        escalation_reasons.append("A representative may help arrange language or accessibility support.")
    if any(item["confidence"]["value"] < 0.6 for item in results[:3]):
        escalation_reasons.append("At least one high-priority match needs more information.")

    reference = f"LM-{secrets.token_hex(3).upper()}"
    handoff = {
        "recommended": bool(escalation_reasons),
        "reasons": escalation_reasons,
        "reference": reference,
        "summary": {
            "location_shared": location,
            "needs": sorted(needs),
            "circumstances": sorted(circumstances),
            "urgency": urgency,
            "top_programs": [item["name"] for item in results[:3]],
        },
        "contacts": [
            {"label": "Emergency", "value": "911", "when": "Immediate danger or life-threatening emergency"},
            {"label": "Virginia 211", "value": "Dial 211", "when": "Local services, shelter, food, or a live navigator"},
            {"label": "Relay", "value": "Dial 711", "when": "Telecommunications relay support"},
        ],
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "location": location,
        "recommendations": results[:8],
        "handoff": handoff,
        "privacy": {
            "stored": False,
            "used": ["location you entered", "selected needs", "selected circumstances", "urgency"],
            "not_requested": ["Social Security number", "income amount", "bank information", "document uploads"],
            "message": "Your answers were used for this response and were not written to the application database.",
        },
        "empty_notice": None
        if results
        else "No confident program match was found. Virginia 211 can help a person review your situation.",
        "engine": "deterministic eligibility rules; Foundry explains but never decides",
    }
