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


def test_fraud_and_speech_contracts():
    fraud = client.post(
        "/api/fraud-check",
        json={"text": "Pay a fee by gift card now and send your bank password."},
    )
    assert fraud.status_code == 200
    assert fraud.json()["risk"] == "high"

    speech = client.post("/api/speech", json={"text": "Verified guidance", "language": "en"})
    assert speech.status_code in {200, 503}
