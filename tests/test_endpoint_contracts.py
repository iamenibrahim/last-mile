from fastapi.testclient import TestClient

from api.main import app


client = TestClient(app)


def test_read_endpoints_return_expected_contracts():
    assert client.get("/healthz").json() == {"ok": True}
    assert client.get("/api/status").json()["status"] == "ready"
    assert "environment" in client.get("/api/config").json()
    assert client.get("/api/alerts").json()["features"]
    assert "status" in client.get("/api/evaluation").json() or "generated_at" in client.get(
        "/api/evaluation"
    ).json()
    assert client.get("/api/status").json()["languages"] == {
        "en": "English",
        "es": "Spanish",
        "ar": "Arabic",
        "prs": "Dari",
        "tl": "Tagalog",
    }


def test_packet_intake_continue_and_verify_contracts():
    next_question = client.post("/api/intake/next", json={"location": "24370"})
    assert next_question.status_code == 200
    assert next_question.json()["question"]["id"] == "jurisdiction"

    packet_response = client.post(
        "/api/packet",
        json={
            "location": "24370",
            "jurisdiction": "Smyth County",
            "needs": ["housing"],
            "circumstances": ["displaced"],
            "context_reviewed": True,
        },
    )
    assert packet_response.status_code == 200
    packet = packet_response.json()["packet"]
    assert client.post("/api/packet/verify", json={"packet": packet}).json()["valid"] is True
    resumed = client.get(f"/api/continue/{packet['continuity']['code']}")
    assert resumed.status_code == 200
    assert resumed.json()["resumed"] is True

    handoff = client.get(f"/api/handoff/{packet['continuity']['code'].lower()}").json()
    assert handoff["packet_verified"] is True
    assert handoff["jurisdiction"] == "Smyth County"
    assert handoff["disaster_id"] == packet["disaster"]["id"]
    assert [action["label"] for action in handoff["actions"]] == [
        action["label"] for action in packet["actions"]
    ]
    assert all(action["source_url"].startswith("https://") for action in handoff["actions"])
    assert client.get("/api/handoff/RBX-NOPE0").status_code == 404


def test_fraud_and_speech_contracts():
    fraud = client.post(
        "/api/fraud-check",
        json={"text": "Pay a fee by gift card now and send your bank password."},
    )
    assert fraud.status_code == 200
    assert fraud.json()["risk"] == "high"

    speech = client.post("/api/speech", json={"text": "Verified guidance", "language": "en"})
    assert speech.status_code in {200, 503}


def test_voice_call_endpoint_is_fail_closed_without_azure_configuration():
    packet = client.post(
        "/api/packet",
        json={
            "location": "24370",
            "jurisdiction": "Smyth County",
            "needs": ["housing"],
            "circumstances": ["displaced"],
            "context_reviewed": True,
        },
    ).json()["packet"]
    result = client.post(
        "/api/calls/start",
        json={
            "continuity_code": packet["continuity"]["code"],
            "phone_number": "+17035550123",
            "consent": True,
        },
    )
    assert result.status_code == 503


def test_grounded_evidence_pipeline_is_mounted():
    with TestClient(app) as started:
        health = started.get("/grounded/api/health")
        assert health.status_code == 200
        assert started.get("/grounded/api/corpus/stats").json()
        page = started.get("/grounded/")
        assert page.status_code == 200 and "assist.js" in page.text
        result = started.post(
            "/grounded/api/assist",
            json={"county_fips": "51173", "needs": ["home_damaged"], "lang": "en"},
        )
        assert result.status_code == 200


def test_signing_key_endpoint_is_honest_about_the_local_key():
    described = client.get("/api/signing-key").json()
    assert described["algorithm"] in {"HMAC-SHA256", "RS256"}
    assert described["publicly_verifiable"] is (described["algorithm"] == "RS256")
