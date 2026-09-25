from __future__ import annotations

import json
import os
from collections import defaultdict, deque
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from threading import Lock
from time import monotonic
from typing import Any
from urllib.parse import urlsplit


DEFAULT_REVIEW_INTERVAL_DAYS = 90
PROGRAM_REQUIRED_FIELDS = (
    "id",
    "name",
    "agency",
    "needs",
    "eligibility",
    "apply_url",
    "source_url",
    "source_excerpt",
    "last_verified",
    "expiration_date",
    "disaster_id",
    "review_interval_days",
)
REVIEWED_PROGRAM_DOMAINS = frozenset(
    {
        "211virginia.org",
        "commonhelp.virginia.gov",
        "www.disasterassistance.gov",
        "www.dol.gov",
        "www.fema.gov",
        "www.fns.usda.gov",
        "www.lsc.gov",
        "www.ready.gov",
        "www.samhsa.gov",
        "www.sba.gov",
        "www.usa.gov",
        "www.vaemergency.gov",
        "www.vec.virginia.gov",
    }
)
REVIEWED_TEL_LINKS = frozenset({"tel:911"})
COMPARABLE_CLAIM_FIELDS = {
    "deadline": "application_deadline",
    "application_deadline": "application_deadline",
    "phone": "contact_phone",
    "phone_number": "contact_phone",
    "contact_phone": "contact_phone",
    "eligibility": "eligibility_condition",
    "eligibility_condition": "eligibility_condition",
    "eligibility_conditions": "eligibility_condition",
    "status": "program_status",
    "program_status": "program_status",
    "program_open_status": "program_status",
}
ACCESSIBILITY_PREFERENCES = {
    "screen_reader": "Use semantic headings, concise labels, and no visual-only instructions.",
    "large_text": "Prefer large text and short blocks in the web view.",
    "low_bandwidth": "Prefer text, cached sources, and no optional maps or model calls.",
    "voice_preferred": "Lead with the verified voice script and spoken recovery code.",
    "relay_service": "Include 711 telecommunications relay instructions.",
}


def _program_error(
    index: int,
    program_id: Any,
    field: str,
    code: str,
    message: str,
) -> dict[str, Any]:
    return {
        "record_index": index,
        "program_id": program_id if isinstance(program_id, str) else None,
        "field": field,
        "code": code,
        "message": message,
    }


def validate_program_records(records: Any) -> dict[str, Any]:
    """Validate the reviewed program catalog with precise, field-level errors."""

    errors: list[dict[str, Any]] = []
    if not isinstance(records, list):
        errors.append(_program_error(-1, None, "$", "invalid_type", "program catalog must be a JSON array"))
        return {"valid": False, "record_count": 0, "errors": errors}

    seen_ids: dict[str, int] = {}
    required_strings = {
        "id",
        "name",
        "agency",
        "eligibility",
        "apply_url",
        "source_url",
        "source_excerpt",
        "last_verified",
        "disaster_id",
    }
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(
                _program_error(index, None, "$", "invalid_type", "program record must be a JSON object")
            )
            continue
        program_id = record.get("id")
        for field in PROGRAM_REQUIRED_FIELDS:
            if field not in record:
                errors.append(
                    _program_error(index, program_id, field, "required", f"{field} is required")
                )
        for field in required_strings:
            if field in record and (not isinstance(record[field], str) or not record[field].strip()):
                errors.append(
                    _program_error(
                        index,
                        program_id,
                        field,
                        "invalid_type",
                        f"{field} must be a non-empty string",
                    )
                )

        if isinstance(program_id, str) and program_id:
            if program_id in seen_ids:
                errors.append(
                    _program_error(
                        index,
                        program_id,
                        "id",
                        "duplicate",
                        f"id duplicates record {seen_ids[program_id]}",
                    )
                )
            else:
                seen_ids[program_id] = index

        needs = record.get("needs")
        if "needs" in record and (
            not isinstance(needs, list)
            or not needs
            or any(not isinstance(item, str) or not item.strip() for item in needs)
        ):
            errors.append(
                _program_error(
                    index,
                    program_id,
                    "needs",
                    "invalid_type",
                    "needs must be a non-empty array of non-empty strings",
                )
            )

        for field in ("last_verified", "expiration_date"):
            value = record.get(field)
            if field == "expiration_date" and field in record and value is None:
                continue
            if field not in record or not isinstance(value, str) or not value:
                continue
            try:
                date.fromisoformat(value)
            except ValueError:
                errors.append(
                    _program_error(
                        index,
                        program_id,
                        field,
                        "invalid_iso_date",
                        f"{field} must be an ISO date in YYYY-MM-DD format",
                    )
                )

        interval = record.get("review_interval_days")
        if "review_interval_days" in record and (
            isinstance(interval, bool) or not isinstance(interval, int) or interval < 1
        ):
            errors.append(
                _program_error(
                    index,
                    program_id,
                    "review_interval_days",
                    "invalid_value",
                    "review_interval_days must be a positive integer",
                )
            )

        for field in ("apply_url", "source_url"):
            value = record.get(field)
            if not isinstance(value, str) or not value:
                continue
            parsed = urlsplit(value)
            if field == "apply_url" and parsed.scheme == "tel":
                if value not in REVIEWED_TEL_LINKS:
                    errors.append(
                        _program_error(
                            index,
                            program_id,
                            field,
                            "unreviewed_tel_link",
                            f"{field} tel link is not in the reviewed emergency-link allowlist",
                        )
                    )
                continue
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                errors.append(
                    _program_error(
                        index,
                        program_id,
                        field,
                        "invalid_url",
                        f"{field} must be an HTTPS URL without embedded credentials",
                    )
                )
            elif parsed.hostname.lower() not in REVIEWED_PROGRAM_DOMAINS:
                errors.append(
                    _program_error(
                        index,
                        program_id,
                        field,
                        "unreviewed_domain",
                        f"{field} domain is not in the reviewed allowlist",
                    )
                )

    return {"valid": not errors, "record_count": len(records), "errors": errors}


def assert_valid_program_records(records: Any) -> list[dict[str, Any]]:
    report = validate_program_records(records)
    if report["valid"]:
        return records
    summary = "; ".join(
        f"record {error['record_index']} field {error['field']}: {error['message']}"
        for error in report["errors"][:5]
    )
    raise ValueError(f"Invalid reviewed program catalog: {summary}")


def _date(value: str | None) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def assess_freshness(record: dict[str, Any], *, today: date | None = None) -> dict[str, Any]:
    """Return a deterministic freshness decision for a reviewed source record."""

    now = today or datetime.now(timezone.utc).date()
    reviewed_raw = record.get("last_verified")
    expiration_present = "expiration_date" in record
    expiration_raw = record.get("expiration_date")
    reviewed = _date(reviewed_raw)
    expires = _date(expiration_raw)
    interval_raw = record.get("review_interval_days")
    interval_valid = (
        not isinstance(interval_raw, bool)
        and isinstance(interval_raw, int)
        and interval_raw > 0
    )
    interval = interval_raw if interval_valid else DEFAULT_REVIEW_INTERVAL_DAYS
    reasons: list[str] = []
    reason_codes: list[str] = []
    if reviewed_raw in (None, ""):
        reason_codes.append("missing_last_verified")
        reasons.append("last_verified is missing")
    elif reviewed is None:
        reason_codes.append("invalid_last_verified")
        reasons.append("last_verified must be an ISO date in YYYY-MM-DD format")
    elif reviewed > now:
        reason_codes.append("future_last_verified")
        reasons.append("last_verified is in the future; source review cannot be verified")
    elif (now - reviewed).days > interval:
        reason_codes.append("review_overdue")
        reasons.append(f"source review is older than {interval} days")
    if not expiration_present:
        reason_codes.append("missing_expiration_date")
        reasons.append("expiration_date is missing; use null for a non-expiring record")
    elif expiration_raw is not None and expires is None:
        reason_codes.append("invalid_expiration_date")
        reasons.append("expiration_date must be an ISO date in YYYY-MM-DD format or null")
    elif expires and expires < now:
        reason_codes.append("expired")
        reasons.append(f"record expired on {expires.isoformat()}")
    if not interval_valid:
        reason_codes.append("invalid_review_interval")
        reasons.append(
            f"review_interval_days is invalid; defaulted to {DEFAULT_REVIEW_INTERVAL_DAYS} days"
        )
    stale = bool(reasons)
    return {
        "status": "stale" if stale else "current",
        "stale": stale,
        "as_of": now.isoformat(),
        "last_verified": reviewed.isoformat() if reviewed else None,
        "expiration_date": expires.isoformat() if expires else None,
        "review_interval_days": interval,
        "review_due_date": (reviewed + timedelta(days=interval)).isoformat() if reviewed else None,
        "days_since_review": (now - reviewed).days if reviewed else None,
        "reason_codes": reason_codes,
        "reasons": reasons,
        "caveat": (
            "Confirm time-sensitive details with the linked agency or a human navigator before relying on this recommendation."
            if stale
            else None
        ),
    }


def evidence_trace(
    program: dict[str, Any],
    matched_needs: list[str],
    matched_circumstances: list[str],
    confidence: dict[str, Any],
) -> dict[str, Any]:
    triggered = []
    if matched_needs:
        triggered.append(f"need intersects program.needs: {', '.join(matched_needs)}")
    if matched_circumstances:
        triggered.append(
            f"circumstance intersects program.circumstances: {', '.join(matched_circumstances)}"
        )
    return {
        "rule": " AND/OR ".join(triggered) or "urgent program + time-sensitive request",
        "source_record": {
            "program_id": program.get("id"),
            "source_label": program.get("source_label"),
            "source_url": program.get("source_url"),
            "disaster_id": program.get("disaster_id"),
        },
        "source_excerpt": program.get("source_excerpt") or program.get("summary"),
        "last_reviewed": program.get("last_verified"),
        "confidence": confidence,
        "caveat": program.get("evidence_caveat")
        or "Screening match only; the authoritative agency decides eligibility and current availability.",
    }


def provenance_graph(program: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    nodes = [
        {"id": "government_source", "label": program.get("source_label"), "kind": "source"},
        {"id": "reviewed_record", "label": program.get("id"), "kind": "review"},
        {"id": "matching_rule", "label": trace["rule"], "kind": "rule"},
        {"id": "recommendation", "label": program.get("name"), "kind": "output"},
        {"id": "verification", "label": "freshness + contradiction checks", "kind": "verification"},
    ]
    return {
        "nodes": nodes,
        "edges": [
            ["government_source", "reviewed_record"],
            ["reviewed_record", "matching_rule"],
            ["matching_rule", "recommendation"],
            ["recommendation", "verification"],
        ],
    }


def detect_source_conflicts(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare only explicitly safe claim fields and never choose a winner."""

    values: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        for claim in record.get("authoritative_claims", []):
            raw_field = str(claim.get("field") or "").strip().lower()
            key = COMPARABLE_CLAIM_FIELDS.get(raw_field)
            raw_value = claim.get("value")
            if key and raw_value is not None and str(raw_value).strip():
                value = str(raw_value).strip()
                if key == "contact_phone":
                    normalized = "".join(character for character in value if character.isdigit())
                elif key == "application_deadline":
                    parsed = _date(value)
                    normalized = parsed.isoformat() if parsed else value
                else:
                    normalized = " ".join(value.split()).casefold()
                values[key].append(
                    {
                        "value": value,
                        "normalized_value": normalized,
                        "source_id": record.get("id"),
                        "source_url": record.get("source_url") or record.get("url"),
                    }
                )
    conflicts = []
    for field in sorted(values):
        claims = sorted(
            values[field],
            key=lambda item: (
                str(item.get("source_id") or ""),
                str(item.get("source_url") or ""),
                item["value"],
            ),
        )
        distinct = {item["normalized_value"] for item in claims}
        if len(distinct) > 1:
            conflicts.append({"field": field, "claims": claims})
    return {
        "conflict_detected": bool(conflicts),
        "conflicts": conflicts,
        "action": "route_to_human_verification" if conflicts else "continue",
    }


def detect_packet_contradictions(packet: dict[str, Any]) -> dict[str, Any]:
    """Check structured facts against every rendered channel, beyond entity locking."""

    disaster_id = str(packet.get("disaster", {}).get("id") or "")
    jurisdiction = str(packet.get("jurisdiction") or "")
    deadline = str((packet.get("deadlines") or [{}])[0].get("value") or "")
    expected = {
        "disaster.id": disaster_id,
        "jurisdiction": jurisdiction,
        "deadline.value": deadline,
    }
    contradictions: list[dict[str, Any]] = []
    for channel_name, channel in packet.get("channels", {}).items():
        blob = json.dumps(channel, ensure_ascii=False)
        locked = {str(value) for value in channel.get("locked_facts", [])}
        for field, value in expected.items():
            if value and value not in blob and value not in locked:
                contradictions.append(
                    {"channel": channel_name, "field": field, "expected": value, "reason": "missing"}
                )
    for action in packet.get("actions", []):
        if action.get("source_id") and action["source_id"] not in {
            source.get("id") for source in packet.get("sources", [])
        }:
            contradictions.append(
                {
                    "channel": "packet",
                    "field": "action.source_id",
                    "expected": action["source_id"],
                    "reason": "unknown_source",
                }
            )
    return {
        "passed": not contradictions,
        "contradiction_detected": bool(contradictions),
        "contradictions": contradictions,
        "action": "withhold_and_route_to_human" if contradictions else "render",
    }


def compile_accessibility(preferences: list[str] | None) -> dict[str, Any]:
    normalized = sorted({item for item in preferences or [] if item in ACCESSIBILITY_PREFERENCES})
    return {
        "preferences": normalized,
        "directives": [ACCESSIBILITY_PREFERENCES[item] for item in normalized],
        "contains_sensitive_data": False,
        "preferred_channel": "voice" if "voice_preferred" in normalized else "web",
        "relay_contact": "711" if "relay_service" in normalized else None,
        "low_bandwidth": "low_bandwidth" in normalized,
    }


CHAOS_FALLBACKS = {
    "foundry_down": ("Microsoft Foundry", "deterministic rules + reviewed copy"),
    "translator_down": ("Azure Translator", "verified English source + interpreter/211 path"),
    "maps_down": ("Azure Maps", "local CAP geometry + text location result"),
    "stale_source": ("source freshness", "visible stale flag + human verification"),
    "bad_translation": ("translation verification", "withhold failed segment + exact English"),
    "no_network": ("network", "signed offline snapshot + cached app shell"),
}


def evaluate_chaos(modes: list[str]) -> dict[str, Any]:
    normalized = [item for item in modes if item in CHAOS_FALLBACKS]
    outcomes = [
        {"failure": mode, "component": CHAOS_FALLBACKS[mode][0], "fallback": CHAOS_FALLBACKS[mode][1], "safe": True}
        for mode in normalized
    ]
    return {
        "simulated": True,
        "modes": normalized,
        "outcomes": outcomes,
        "render_policy": "fallback_only" if normalized else "normal",
        "notice": "Simulation changes no provider or stored data.",
    }


def diff_packet(old: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "deadline": (
            (old.get("deadlines") or [{}])[0].get("value"),
            (current.get("deadlines") or [{}])[0].get("value"),
        ),
        "program_status": (old.get("disaster", {}).get("status"), current.get("disaster", {}).get("status")),
        "snapshot_as_of": (old.get("snapshot", {}).get("as_of"), current.get("snapshot", {}).get("as_of")),
        "source_hashes": (old.get("proof", {}).get("source_hashes"), current.get("proof", {}).get("source_hashes")),
    }
    changes = [
        {"field": field, "old": before, "new": after}
        for field, (before, after) in checks.items()
        if before != after
    ]
    return {"changed": bool(changes), "changes": changes, "message": "Source state changed." if changes else "No reviewed source changes detected."}


def offline_snapshot(
    packet: dict[str, Any],
    verification: dict[str, Any],
    signing_key: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "format": "last-mile-offline-snapshot-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "packet": deepcopy(packet),
        "sources": deepcopy(packet.get("sources", [])),
        "verification_at_export": verification,
        "local_verification": {
            "algorithm": packet.get("proof", {}).get("algorithm"),
            "key_id": packet.get("proof", {}).get("key_id"),
            "packet_sha256": packet.get("proof", {}).get("packet_sha256"),
            "channels_sha256": packet.get("proof", {}).get("channels_sha256"),
            "public_jwk": (signing_key or {}).get("public_jwk"),
            "canonicalization": "UTF-8 JSON; keys sorted; separators ',' and ':'; proof signature, key_id, and algorithm omitted before signature verification",
            "publicly_verifiable": bool((signing_key or {}).get("public_jwk")),
        },
    }


class SurgeController:
    """Small process-local surge signal; it degrades optional work, never core matching."""

    def __init__(self, limit: int | None = None, window_seconds: int = 60):
        self.limit = limit or int(os.getenv("SURGE_REQUESTS_PER_MINUTE", "120"))
        self.window_seconds = window_seconds
        self.events: deque[float] = deque()
        self.lock = Lock()

    def observe(self) -> dict[str, Any]:
        now = monotonic()
        with self.lock:
            while self.events and now - self.events[0] > self.window_seconds:
                self.events.popleft()
            self.events.append(now)
            forced = os.getenv("SURGE_MODE", "false").lower() == "true"
            active = forced or len(self.events) > self.limit
            return {
                "active": active,
                "requests_in_window": len(self.events),
                "threshold": self.limit,
                "mode": "surge" if active else "normal",
                "degradation": [
                    "deterministic matching retained",
                    "AI explanations optional",
                    "cached translations preferred",
                    "optional maps skipped",
                ] if active else [],
            }


surge_controller = SurgeController()
