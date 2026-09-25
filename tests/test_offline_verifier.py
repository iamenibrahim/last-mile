"""Production-style, network-free RS256 snapshot verification."""

import base64
import json
import socket
from copy import deepcopy

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from api.protocol import _packet_message, build_action_packet, verify_action_packet
from api.reliability import offline_snapshot
from scripts.verify_offline_snapshot import main, verify_snapshot


PROFILE = {
    "location": "24370",
    "jurisdiction": "Smyth County",
    "needs": ["housing"],
    "circumstances": ["displaced"],
    "context_reviewed": True,
}


def _b64url(number: int) -> str:
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


@pytest.fixture()
def rs256_fixture(tmp_path):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = private_key.public_key().public_numbers()
    key_id = "https://trusted.example/keys/last-mile-test/1"
    public_jwk = {
        "kty": "RSA",
        "alg": "RS256",
        "kid": key_id,
        "n": _b64url(numbers.n),
        "e": _b64url(numbers.e),
    }
    packet = build_action_packet(PROFILE)["packet"]
    packet["proof"].update({"algorithm": "RS256", "key_id": key_id})
    packet["proof"]["signature"] = private_key.sign(
        _packet_message(packet), padding.PKCS1v15(), hashes.SHA256()
    ).hex()
    snapshot = offline_snapshot(packet, {"valid": True}, {"public_jwk": public_jwk})
    snapshot_path = tmp_path / "production-style-snapshot.json"
    trusted_key_path = tmp_path / "trusted-public-jwk.json"
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
    trusted_key_path.write_text(json.dumps(public_jwk), encoding="utf-8")
    return snapshot, snapshot_path, public_jwk, trusted_key_path


def test_production_style_rs256_snapshot_verifies_without_network(monkeypatch, rs256_fixture):
    snapshot, snapshot_path, public_jwk, _ = rs256_fixture

    def network_forbidden(*args, **kwargs):
        raise AssertionError("offline verification attempted network access")

    monkeypatch.setattr(socket, "create_connection", network_forbidden)
    report = verify_snapshot(snapshot_path, trusted_jwk=public_jwk)
    assert report["valid"] is True
    assert report["signature_valid"] is True
    assert report["trust_anchor"] == "trusted_jwk_file"
    assert report["embedded_key_matches_trusted"] is True
    assert report["channels_valid"] is True
    assert report["sources_match_packet"] is True
    assert report["field_consistency"]["passed"] is True
    assert report["source_conflicts"]["conflict_detected"] is False
    assert not ({"d", "p", "q", "dp", "dq", "qi"} & set(snapshot["local_verification"]["public_jwk"]))


def test_embedded_key_alone_is_not_a_trust_anchor(rs256_fixture):
    _, snapshot_path, _, _ = rs256_fixture
    report = verify_snapshot(snapshot_path)
    assert report["valid"] is False
    assert report["signature_check"] == "unavailable_without_trusted_public_key"
    assert report["trust_anchor"] == "missing"


def test_channel_and_source_tampering_fail_independent_checks(tmp_path, rs256_fixture):
    snapshot, _, public_jwk, _ = rs256_fixture

    channel_tamper = deepcopy(snapshot)
    channel_tamper["packet"]["channels"]["voice"]["script"] = "Altered channel"
    channel_path = tmp_path / "channel-tamper.json"
    channel_path.write_text(json.dumps(channel_tamper), encoding="utf-8")
    channel_report = verify_snapshot(channel_path, trusted_jwk=public_jwk)
    assert channel_report["valid"] is False
    assert channel_report["signature_valid"] is False
    assert channel_report["channels_valid"] is False

    signed_source_tamper = deepcopy(snapshot)
    signed_source_tamper["packet"]["sources"][0]["title"] = "Altered source"
    signed_source_path = tmp_path / "signed-source-tamper.json"
    signed_source_path.write_text(json.dumps(signed_source_tamper), encoding="utf-8")
    signed_source_report = verify_snapshot(signed_source_path, trusted_jwk=public_jwk)
    assert signed_source_report["valid"] is False
    assert signed_source_report["signature_valid"] is False
    assert signed_source_report["sources_match_packet"] is False

    outer_source_tamper = deepcopy(snapshot)
    outer_source_tamper["sources"] = [{"id": "unsigned-source"}]
    outer_source_path = tmp_path / "outer-source-tamper.json"
    outer_source_path.write_text(json.dumps(outer_source_tamper), encoding="utf-8")
    outer_source_report = verify_snapshot(outer_source_path, trusted_jwk=public_jwk)
    assert outer_source_report["signature_valid"] is True
    assert outer_source_report["sources_match_packet"] is False
    assert outer_source_report["valid"] is False


def test_cli_output_is_bounded_json_suitable_for_demo(capsys, rs256_fixture):
    _, snapshot_path, _, trusted_key_path = rs256_fixture
    assert main([str(snapshot_path), "--trusted-jwk", str(trusted_key_path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["schema_version"] == "offline-verification-v2"
    assert report["valid"] is True
    assert report["trusted_key_sha256"] and len(report["trusted_key_sha256"]) == 64
    assert "packet" not in report and "signature" not in report


def test_malformed_json_returns_safe_useful_cli_error(tmp_path, capsys, rs256_fixture):
    _, _, _, trusted_key_path = rs256_fixture
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{not-json", encoding="utf-8")
    assert main([str(malformed), "--trusted-jwk", str(trusted_key_path)]) == 2
    assert json.loads(capsys.readouterr().out) == {
        "schema_version": "offline-verification-v2",
        "valid": False,
        "error": "malformed_snapshot_json",
    }


def test_local_hmac_snapshot_cannot_be_independently_verified(tmp_path):
    packet = build_action_packet(PROFILE)["packet"]
    assert packet["proof"]["algorithm"] == "HMAC-SHA256"
    snapshot = offline_snapshot(packet, verify_action_packet(packet))
    path = tmp_path / "local-hmac-snapshot.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    report = verify_snapshot(path)
    assert report["valid"] is False
    assert report["signature_check"] == "unavailable_without_trusted_public_key"
    assert snapshot["local_verification"]["public_jwk"] is None
