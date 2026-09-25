from __future__ import annotations

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.protocol import _canonical, _hash
from api.reliability import detect_packet_contradictions, detect_source_conflicts
from api.signing import verify_with_public_jwk


FORMAT = "last-mile-offline-snapshot-v1"
REPORT_VERSION = "offline-verification-v2"


class SnapshotVerificationError(ValueError):
    """A bounded, public-safe snapshot diagnostic."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _object(value: Any, code: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SnapshotVerificationError(code)
    return value


def _read_json(path: Path, malformed_code: str) -> dict[str, Any]:
    try:
        return _object(json.loads(path.read_text(encoding="utf-8")), malformed_code)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SnapshotVerificationError(malformed_code) from error


def _validated_public_jwk(value: Any) -> dict[str, Any]:
    jwk = _object(value, "invalid_trusted_jwk")
    required = ("kty", "alg", "kid", "n", "e")
    if jwk.get("kty") != "RSA" or jwk.get("alg") != "RS256" or any(
        not isinstance(jwk.get(field), str) or not jwk[field].strip() for field in required
    ):
        raise SnapshotVerificationError("invalid_trusted_jwk")
    return {field: jwk[field] for field in required}


def jwk_sha256(jwk: dict[str, Any]) -> str:
    """Stable public-key fingerprint; no private material is accepted or emitted."""

    public = _validated_public_jwk(jwk)
    return hashlib.sha256(_canonical(public)).hexdigest()


def verify_snapshot(path: Path, *, trusted_jwk: dict[str, Any] | None = None) -> dict[str, Any]:
    """Verify a snapshot locally. Authenticity requires an independently trusted JWK."""

    snapshot = _read_json(path, "malformed_snapshot_json")
    if snapshot.get("format") != FORMAT:
        raise SnapshotVerificationError("unsupported_snapshot_format")
    packet = _object(snapshot.get("packet"), "missing_packet")
    proof = _object(packet.get("proof"), "malformed_packet_proof")
    channels = _object(packet.get("channels"), "malformed_packet_channels")
    local = _object(snapshot.get("local_verification"), "missing_local_verification")
    embedded_jwk = local.get("public_jwk")
    algorithm = proof.get("algorithm")

    key = _validated_public_jwk(trusted_jwk) if trusted_jwk is not None else None
    embedded_key_valid = False
    embedded_key_matches_trusted = False
    if embedded_jwk is not None:
        try:
            embedded = _validated_public_jwk(embedded_jwk)
            embedded_key_valid = True
            embedded_key_matches_trusted = key is not None and embedded == key
        except SnapshotVerificationError:
            embedded_key_valid = False

    unsigned = deepcopy(packet)
    unsigned_proof = _object(unsigned.get("proof"), "malformed_packet_proof")
    for field in ("signature", "key_id", "algorithm"):
        unsigned_proof.pop(field, None)

    signature_valid = False
    if key is not None and algorithm == "RS256":
        try:
            signature_valid = verify_with_public_jwk(
                key,
                _canonical(unsigned),
                str(proof.get("signature") or ""),
            )
        except (KeyError, TypeError, ValueError):
            signature_valid = False
    key_id_matches = bool(
        key is not None
        and proof.get("key_id") == key.get("kid")
        and local.get("key_id") == key.get("kid")
    )
    channels_valid = proof.get("channels_sha256") == _hash(channels)
    sources_match_packet = snapshot.get("sources") == packet.get("sources")
    field_consistency = detect_packet_contradictions(packet)
    source_conflicts = detect_source_conflicts(packet.get("sources", []))
    valid = all(
        (
            key is not None,
            embedded_key_matches_trusted,
            key_id_matches,
            signature_valid,
            channels_valid,
            sources_match_packet,
            field_consistency["passed"],
            not source_conflicts["conflict_detected"],
        )
    )
    return {
        "schema_version": REPORT_VERSION,
        "valid": valid,
        "signature_valid": signature_valid,
        "signature_check": "verified" if signature_valid else "failed" if key else "unavailable_without_trusted_public_key",
        "trust_anchor": "trusted_jwk_file" if key else "missing",
        "trusted_key_sha256": jwk_sha256(key) if key else None,
        "embedded_key_valid": embedded_key_valid,
        "embedded_key_matches_trusted": embedded_key_matches_trusted,
        "key_id_matches": key_id_matches,
        "channels_valid": channels_valid,
        "sources_match_packet": sources_match_packet,
        "field_consistency": field_consistency,
        "source_conflicts": source_conflicts,
        "limitations": [
            "verification_at_export is informational and is not trusted",
            "created_at is informational and is not signed separately",
        ],
    }


def _error_report(code: str) -> dict[str, Any]:
    return {"schema_version": REPORT_VERSION, "valid": False, "error": code}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a Last-Mile snapshot locally without network access.")
    parser.add_argument("snapshot", type=Path)
    parser.add_argument(
        "--trusted-jwk",
        type=Path,
        required=True,
        help="Public JWK obtained independently from the reviewed deployment or another trusted channel.",
    )
    args = parser.parse_args(argv)
    try:
        trusted_jwk = _read_json(args.trusted_jwk, "malformed_trusted_jwk_json")
        report = verify_snapshot(args.snapshot, trusted_jwk=trusted_jwk)
        status = 0 if report["valid"] else 1
    except SnapshotVerificationError as error:
        report = _error_report(error.code)
        status = 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
