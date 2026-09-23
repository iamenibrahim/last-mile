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

