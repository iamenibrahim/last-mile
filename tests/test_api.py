from fastapi.testclient import TestClient

from api.main import app


client = TestClient(app)


def test_full_navigation_and_verification_flow():
    plan = client.post(
        "/api/navigate",
        json={
            "location": "23510",
            "urgency": "tonight",
            "needs": ["shelter", "food", "documents"],
            "circumstances": ["displaced", "no_id"],
        },
    )
    assert plan.status_code == 200
    assert plan.json()["recommendations"]
    assert plan.json()["alert_context"]["position"]["status"] == "inside"
    assert plan.json()["privacy"]["stored"] is False

    transformed = client.post(
        "/api/transform", json={"language": "en", "grade": 6, "simulate_failure": True}
    )
    assert transformed.status_code == 200
    payload = transformed.json()
    assert any(segment["status"] == "verbatim_abstained" for segment in payload["segments"])
    rendered = "\n".join(segment["output"] for segment in payload["segments"])

    verified = client.post(
        "/api/verify", json={"manifest": payload["manifest"], "rendered_text": rendered}
    )
    assert verified.status_code == 200
    assert verified.json()["valid"] is True


def test_static_app_and_health_are_served():
    assert client.get("/healthz").json() == {"ok": True}
    page = client.get("/")
    assert page.status_code == 200
    assert "The right help" in page.text


def test_historical_protocol_flow_discloses_minimal_retention():
    plan = client.post(
        "/api/navigate",
        json={
            "location": "24370",
            "jurisdiction": "Smyth County",
            "urgency": "safe_now",
            "needs": ["home_repair", "housing", "documents"],
            "circumstances": ["displaced", "no_id"],
            "context_reviewed": True,
        },
    ).json()
    assert plan["protocol"]["status"] == "complete"
    assert plan["privacy"]["stored"] is True
    assert plan["privacy"]["retention"] == "24 hours"
    assert "full screening response is not logged" in plan["privacy"]["message"]
