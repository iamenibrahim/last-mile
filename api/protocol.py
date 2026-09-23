from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import settings


ROOT = Path(__file__).resolve().parents[1]
DISASTERS_PATH = ROOT / "data" / "disasters.json"
CONTINUITY_PATH = ROOT / "data" / "continuity.db"
PROTOCOL_VERSION = "1.0"
POTENTIAL_QUESTION_GROUPS = 17


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _hash(value: dict) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _load_disaster(disaster_id: str = "DR-4831-VA") -> dict:
    records = json.loads(DISASTERS_PATH.read_text(encoding="utf-8"))
    return next(item for item in records if item["id"] == disaster_id)


def next_question(profile: dict) -> dict:
    """Ask only a question whose answer can change packet guidance."""

    location = str(profile.get("location") or "").strip()
    jurisdiction = profile.get("jurisdiction")
    needs = profile.get("needs") or []
    disaster = _load_disaster()
    counties = disaster.get("zip_crosswalk", {}).get(location, [])
    if not location:
        return {
            "complete": False,
            "question": {"id": "location", "label": "What city or ZIP should we check?", "type": "location"},
            "why": "Location changes disaster declarations and nearby services.",
        }
    if len(counties) > 1 and not jurisdiction:
        return {
            "complete": False,
            "question": {
                "id": "jurisdiction",
                "label": "Which county is this location in?",
                "type": "single_choice",
                "choices": counties,
            },
            "why": "This ZIP crosses a county boundary, and declarations are county-specific.",
            "location_precision": "ambiguous_zip",
        }
    if not needs:
        return {
            "complete": False,
            "question": {"id": "needs", "label": "What do you need help with today?", "type": "multi_choice"},
            "why": "Needs determine which program rules can change the plan.",
        }
    needs_that_change_context = {"shelter", "housing", "home_repair", "medical", "transportation", "documents", "money"}
    if (
        needs_that_change_context.intersection(needs)
        and not profile.get("context_reviewed")
        and not profile.get("circumstances")
    ):
        return {
            "complete": False,
            "question": {
                "id": "context",
                "label": "Is there one constraint that changes how you can apply?",
                "type": "adaptive_context",
            },
            "why": "Displacement, lost ID, accessibility, and coverage gaps can change next steps.",
        }
    return {"complete": True, "question": None, "why": "No remaining answer would change current guidance."}


def question_audit(profile: dict) -> dict:
    asked = ["location_and_jurisdiction", "immediate_needs"]
    if profile.get("context_reviewed") or profile.get("circumstances"):
        asked.append("constraints_that_change_the_path")
    return {
        "potential_question_groups": POTENTIAL_QUESTION_GROUPS,
        "asked": len(asked),
        "asked_groups": asked,
        "skipped": POTENTIAL_QUESTION_GROUPS - len(asked),
        "rule": "A question is asked only when its answer can change guidance.",
    }


def _normalize_needs(needs: list[str]) -> list[str]:
    mapping = {
        "home_repair": "home_damage",
        "housing": "temporary_housing",
        "shelter": "temporary_housing",
        "documents": "lost_identification",
        "money": "financial_assistance",
        "job": "lost_work",
    }
    return sorted({mapping.get(item, item) for item in needs})


def _packet_signature(packet: dict) -> str:
    unsigned = deepcopy(packet)
    unsigned.pop("proof", None)
    return hmac.new(settings.manifest_signing_key.encode("utf-8"), _canonical(unsigned), hashlib.sha256).hexdigest()


def _coarse_location(location: str) -> str:
    zip_match = re.search(r"\b\d{5}\b", location)
    if zip_match:
        return zip_match.group(0)
    if len(location) <= 40 and not re.search(r"\d", location):
        return location
    return "Virginia location (exact address not retained)"


def _compile_channels(packet: dict) -> dict:
    jurisdiction = packet["jurisdiction"]
    disaster = packet["disaster"]
    deadline = packet["deadlines"][0]["display"]
    steps = [action["label"] for action in packet["actions"]]
    code = packet["continuity"]["code"]
    proof_id = packet["proof"]["proof_id"]
    locked_facts = [disaster["id"], packet["deadlines"][0]["value"], jurisdiction]
    sms = (
        f"HISTORICAL DEMO — {jurisdiction}: {disaster['id']} Individual Assistance was open in the "
        f"{packet['snapshot']['as_of_label']} snapshot; deadline was {deadline} (passed). "
        f"Reply 1 steps, 2 documents, or 0 human. CONTINUE {code}. Proof {proof_id}."
    )
    voice_steps = " ".join(f"Step {index + 1}. {step}" for index, step in enumerate(steps))
    return {
        "web": {
            "headline": f"Historical recovery replay for {jurisdiction}",
            "status": f"Individual Assistance was open as of {packet['snapshot']['as_of_label']}.",
            "deadline": f"The application deadline was {deadline} and has passed.",
            "steps": steps,
            "proof_id": proof_id,
            "locked_facts": locked_facts,
        },
        "sms": {
            "text": sms[:320],
            "characters": min(len(sms), 320),
            "commands": {"1": "next steps", "2": "document alternatives", "0": "human help"},
            "transport": "preview only; connect Azure Communication Services for delivery",
            "locked_facts": locked_facts,
        },
        "voice": {
            "script": (
                f"Historical demonstration. {jurisdiction} was included in disaster {disaster['id']} "
                f"Individual Assistance as of {packet['snapshot']['as_of_label']}. The deadline was {deadline} and has passed. "
                f"{voice_steps} To continue with a person, use recovery code {code}."
            ),
            "transport": "Azure AI Speech when configured; device speech fallback",
            "locked_facts": locked_facts,
        },
        "offline": {
            "text": "\n".join(
                [
                    "HISTORICAL VERIFIED SNAPSHOT",
                    f"{jurisdiction} · {disaster['name']} · {disaster['id']}",
                    f"Snapshot: {packet['snapshot']['as_of_label']}",
                    f"Deadline in snapshot: {deadline} (now passed)",
                    *[f"{index + 1}. {step}" for index, step in enumerate(steps)],
                    f"Continue: {code} · Proof: {proof_id}",
                ]
            ),
            "cached": True,
            "locked_facts": locked_facts,
        },
    }


class ContinuityStore:
    def __init__(self, path: Path = CONTINUITY_PATH):
        self.path = path
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS continuations (
                    code TEXT PRIMARY KEY,
                    packet_json TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )"""
            )

    def create_code(self) -> str:
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
        return "RBX-" + "".join(secrets.choice(alphabet) for _ in range(5))

    def save(self, packet: dict, hours: int = 24) -> None:
        expires = datetime.now(timezone.utc) + timedelta(hours=hours)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO continuations(code, packet_json, expires_at) VALUES (?, ?, ?)",
                (packet["continuity"]["code"], json.dumps(packet), expires.isoformat()),
            )

    def load(self, code: str) -> dict | None:
        normalized = code.strip().upper()
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT packet_json, expires_at FROM continuations WHERE code = ?", (normalized,)
            ).fetchone()
        if not row or datetime.fromisoformat(row[1]) < datetime.now(timezone.utc):
            return None
        return json.loads(row[0])


continuity_store = ContinuityStore()


def build_action_packet(profile: dict) -> dict:
    next_step = next_question(profile)
    if not next_step["complete"]:
        return {"status": "needs_input", **next_step, "question_audit": question_audit(profile)}

    disaster = _load_disaster()
    location = str(profile.get("location", "Virginia"))
    if not profile.get("jurisdiction") and location not in disaster.get("zip_crosswalk", {}):
        return {
            "status": "no_applicable_snapshot",
            "notice": "No reviewed recovery snapshot is checked in for this location. General program matches remain available.",
            "question_audit": question_audit(profile),
        }
    jurisdiction = profile.get("jurisdiction") or (
        disaster.get("zip_crosswalk", {}).get(location, [None])[0]
    ) or location
    declared = jurisdiction in disaster["individual_assistance_counties"]
    needs = _normalize_needs(profile.get("needs", []))
    circumstances = sorted(set(profile.get("circumstances", [])))
    source_hashes = [{**source, "sha256": _hash(source)} for source in disaster["sources"]]
    deadline = disaster["deadlines"][0]
    actions = []
    if declared and any(need in needs for need in {"home_damage", "temporary_housing", "financial_assistance"}):
        actions.append(
            {
                "priority": 1,
                "action_id": "review_fema_ia_historical_path",
                "label": "Review FEMA housing and home-repair assistance requirements from the historical snapshot.",
                "source_id": "fema-dr-4831",
                "confidence": "authoritative_snapshot",
                "current_limit": "The historical application deadline has passed; ask FEMA or 211 about current recovery options.",
            }
        )
    if "lost_identification" in needs or "no_id" in circumstances:
        actions.append(
            {
                "priority": len(actions) + 1,
                "action_id": "prepare_document_alternatives",
                "label": "Ask which identity alternatives are accepted before sending any documents.",
                "source_id": "fema-dr-4831",
                "confidence": "needs_human_confirmation",
            }
        )
    actions.append(
        {
            "priority": len(actions) + 1,
            "action_id": "confirm_current_options",
            "label": "Confirm current recovery options with FEMA or Virginia 211; do not rely on the closed 2024 deadline.",
            "source_id": "fema-dr-4831",
            "confidence": "authoritative_contact_path",
        }
    )
    code = continuity_store.create_code()
    packet = {
        "protocol": "Last-Mile Protocol",
        "protocol_version": PROTOCOL_VERSION,
        "packet_id": "DAP-" + secrets.token_hex(5).upper(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "jurisdiction": jurisdiction,
        "location_input": _coarse_location(location),
        "disaster": {
            "id": disaster["id"],
            "name": disaster["name"],
            "incident_period": disaster["incident_period"],
            "status": disaster["current_status"],
        },
        "snapshot": {
            "as_of": disaster["snapshot_as_of"],
            "as_of_label": "November 18, 2024 at 8:42 AM ET",
            "status_then": disaster["snapshot_status"],
            "historical": True,
            "notice": disaster["demo_notice"],
        },
        "applicability": {
            "individual_assistance_designated_at_snapshot": declared,
            "method": "jurisdiction membership in the reviewed FEMA designation snapshot",
            "source_id": "fema-dr-4831",
        },
        "needs": needs,
        "constraints": circumstances,
        "deadlines": [
            {
                "id": deadline["id"],
                "value": deadline["value"],
                "display": "December 2, 2024",
                "locked": True,
                "current_status": deadline["current_status"],
                "source_id": deadline["source_id"],
            }
        ],
        "actions": actions,
        "escalation": {
            "required": "no_id" in circumstances or not declared,
            "topic": "Proceeding without identification" if "no_id" in circumstances else "Confirming current options",
            "contact": "FEMA Helpline 800-621-3362 or Virginia 211",
            "read_this": f"I am in {jurisdiction}. I am reviewing DR-4831-VA historical guidance and need current help for: {', '.join(needs)}.",
        },
        "question_audit": question_audit(profile),
        "sources": source_hashes,
        "safety_constraints": [
            "Foundry may transform packet fields but may not originate facts.",
            "Locked deadlines and government identifiers must remain byte-for-byte unchanged.",
            "Every channel must state that this is a historical replay and the deadline passed.",
            "Eligibility remains an agency decision.",
        ],
        "continuity": {
            "code": code,
            "contains": ["county", "disaster id", "broad needs", "constraints", "current step"],
            "excludes": ["name", "street address", "SSN", "bank data", "uploaded documents"],
            "expires_in_hours": 24,
            "resume_command": f"CONTINUE {code}",
        },
    }
    packet["proof"] = {
        "proof_id": "PRF-" + base64.b32encode(bytes.fromhex(_hash(packet))[:5]).decode("ascii").rstrip("="),
        "packet_sha256": _hash(packet),
        "source_hashes": {source["id"]: source["sha256"] for source in source_hashes},
        "locked_facts": [disaster["id"], deadline["value"], jurisdiction],
        "transformation_policy": "channel-compiler-v1",
        "signature_method": "HMAC-SHA256 local demo; Azure Key Vault asymmetric key in production",
        "signature": "pending",
    }
    packet["channels"] = _compile_channels(packet)
    packet["proof"]["channels_sha256"] = _hash(packet["channels"])
    packet["proof"]["signature"] = _packet_signature(packet)
    continuity_store.save(packet)
    return {"status": "complete", "packet": packet}


def verify_action_packet(packet: dict) -> dict:
    supplied = packet.get("proof", {}).get("signature", "")
    expected = _packet_signature(packet)
    deadline = packet.get("deadlines", [{}])[0].get("value")
    channel_blob = json.dumps(packet.get("channels", {}), ensure_ascii=False)
    locked_present = all(str(value) in channel_blob for value in [deadline, packet.get("disaster", {}).get("id"), packet.get("jurisdiction")])
    channels_valid = hmac.compare_digest(
        packet.get("proof", {}).get("channels_sha256", ""), _hash(packet.get("channels", {}))
    )
    return {
        "valid": hmac.compare_digest(supplied, expected) and locked_present and channels_valid,
        "signature_valid": hmac.compare_digest(supplied, expected),
        "channels_valid": channels_valid,
        "locked_facts_present_across_compiled_state": locked_present,
        "proof_id": packet.get("proof", {}).get("proof_id"),
    }


def compile_alert_packet(alert: dict, segments: list[dict], manifest: dict) -> dict:
    """Compile a verified during-disaster state into the same four channel shapes."""

    properties = alert.get("properties", {})
    verified_actions = [
        item["output"] for item in segments if item["section"] == "instruction"
    ]
    headline = next(
        (item["output"] for item in segments if item["section"] == "headline"),
        properties.get("headline", "Emergency alert"),
    )
    locked_facts = sorted(
        {
            entity["value"]
            for segment in segments
            for entity in segment.get("entities", [])
        }
        | {str(manifest["source"]["cap_id"])}
    )
    proof_id = "PRF-" + manifest["signature"][:10].upper()
    sms = f"{headline} " + " ".join(
        f"{index + 1}) {action}" for index, action in enumerate(verified_actions)
    )
    channels = {
        "web": {
            "headline": headline,
            "steps": verified_actions,
            "locked_facts": locked_facts,
        },
        "sms": {
            "text": sms[:320],
            "characters": min(len(sms), 320),
            "locked_facts": locked_facts,
        },
        "voice": {
            "script": headline + " " + " ".join(
                f"Step {index + 1}. {action}" for index, action in enumerate(verified_actions)
            ),
            "locked_facts": locked_facts,
        },
        "offline": {
            "text": "\n".join([headline, *verified_actions, f"Proof: {proof_id}"]),
            "cached": True,
            "locked_facts": locked_facts,
        },
    }
    return {
        "protocol": "Last-Mile Protocol",
        "protocol_version": PROTOCOL_VERSION,
        "phase": "before_during",
        "authority": "NWS CAP schema",
        "government_id": manifest["source"]["cap_id"],
        "geographic_applicability": properties.get("areaDesc"),
        "timing": {
            "onset": properties.get("onset"),
            "effective": properties.get("effective"),
            "expires": properties.get("expires"),
        },
        "instructions_only_from_cap": True,
        "channels": channels,
        "proof": {
            "proof_id": proof_id,
            "source_sha256": manifest["source"]["sha256"],
            "manifest_signature": manifest["signature"],
            "channels_sha256": _hash(channels),
            "locked_facts": locked_facts,
            "trust_boundary": manifest["trust_boundary"],
        },
    }
