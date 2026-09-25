from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.protocol import _canonical, _hash
from api.reliability import detect_packet_contradictions
from api.signing import verify_with_public_jwk


def verify_snapshot(path: Path) -> dict:
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    packet = snapshot["packet"]
    proof = packet.get("proof", {})
    unsigned = deepcopy(packet)
    for field in ("signature", "key_id", "algorithm"):
        unsigned.get("proof", {}).pop(field, None)
    public_jwk = snapshot.get("local_verification", {}).get("public_jwk")
    signature_valid = None
    if public_jwk and proof.get("algorithm") == "RS256":
        signature_valid = verify_with_public_jwk(public_jwk, _canonical(unsigned), proof.get("signature", ""))
    channels_valid = proof.get("channels_sha256") == _hash(packet.get("channels", {}))
    field_consistency = detect_packet_contradictions(packet)
    result = {
        "signature_valid": signature_valid,
        "signature_check": "verified" if signature_valid else "failed" if signature_valid is False else "unavailable_without_public_key",
        "channels_valid": channels_valid,
        "field_consistency": field_consistency,
        "valid": signature_valid is True and channels_valid and field_consistency["passed"],
    }
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify a Last-Mile signed snapshot without network access.")
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    report = verify_snapshot(args.snapshot)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["valid"] else 1)
