"""Bounded mutation properties for the four compiled action-packet channels."""

from copy import deepcopy
from typing import Any

import pytest

from api.protocol import _hash, build_action_packet, verify_action_packet
from api.reliability import detect_packet_contradictions


PROFILE = {
    "location": "24370",
    "jurisdiction": "Smyth County",
    "needs": ["housing"],
    "circumstances": ["displaced"],
    "context_reviewed": True,
}
CHANNELS = ("web", "sms", "voice", "offline")
MUTATIONS = (
    ("jurisdiction", "Smyth County", "Washington County"),
    ("disaster.id", "DR-4831-VA", "DR-9999-VA"),
    ("deadline.value", "December 2, 2024", "December 20, 2024"),
    ("escalation.contact_phone", "800-621-3362", "800-555-0100"),
)
HARMLESS_FORMATS = (
    ("Smyth County", "  SMYTH   COUNTY  "),
    ("DR-4831-VA", "dr-4831-va"),
    ("December 2, 2024", "DECEMBER 2, 2024"),
    ("800-621-3362", "(800) 621-3362"),
)


@pytest.fixture(scope="module")
def baseline_packet() -> dict[str, Any]:
    packet = build_action_packet(PROFILE)["packet"]
    assert detect_packet_contradictions(packet)["passed"] is True
    return packet


def _replace_rendered(value: Any, old: str, new: str, *, key: str = "") -> tuple[Any, int]:
    """Replace visible strings while leaving lock metadata untouched."""

    if key == "locked_facts":
        return deepcopy(value), 0
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        count = 0
        for child_key, child in value.items():
            result[child_key], child_count = _replace_rendered(child, old, new, key=child_key)
            count += child_count
        return result, count
    if isinstance(value, list):
        result = []
        count = 0
        for child in value:
            changed, child_count = _replace_rendered(child, old, new, key=key)
            result.append(changed)
            count += child_count
        return result, count
    if isinstance(value, str):
        return value.replace(old, new), value.count(old)
    return deepcopy(value), 0


def _mutate_one(packet: dict[str, Any], channel: str, old: str, new: str) -> dict[str, Any]:
    mutated = deepcopy(packet)
    mutated_channel, replacements = _replace_rendered(mutated["channels"][channel], old, new)
    assert replacements == 1, f"expected one visible {old!r} occurrence in {channel}, got {replacements}"
    mutated["channels"][channel] = mutated_channel
    return mutated


def test_locked_fact_mutation_matrix_is_bounded_and_every_case_is_detected(baseline_packet):
    cases = [(channel, *mutation) for channel in CHANNELS for mutation in MUTATIONS]
    assert len(cases) == 16
    for channel, field, old, new in cases:
        report = detect_packet_contradictions(_mutate_one(baseline_packet, channel, old, new))
        assert report["contradiction_detected"] is True, (channel, field)
        assert any(
            item["channel"] == channel and item["field"] == field
            for item in report["contradictions"]
        ), (channel, field, report)


def test_harmless_formatting_matrix_has_no_field_contradictions(baseline_packet):
    cases = [(channel, *formatting) for channel in CHANNELS for formatting in HARMLESS_FORMATS]
    assert len(cases) == 16
    for channel, old, formatted in cases:
        report = detect_packet_contradictions(_mutate_one(baseline_packet, channel, old, formatted))
        assert report["passed"] is True, (channel, old, report)


def test_recomputed_channel_hash_cannot_bypass_signature_or_field_checks(baseline_packet):
    assert len(CHANNELS) == 4
    for channel in CHANNELS:
        mutated = _mutate_one(baseline_packet, channel, "Smyth County", "Washington County")
        mutated["proof"]["channels_sha256"] = _hash(mutated["channels"])
        verified = verify_action_packet(mutated)
        assert verified["channels_valid"] is True, channel
        assert verified["signature_valid"] is False, channel
        assert verified["field_consistency"]["contradiction_detected"] is True, channel
        assert verified["valid"] is False, channel
