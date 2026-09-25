from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from fastapi.middleware.asyncexitstack import AsyncExitStackMiddleware

from api.main import app


PROFILE = {"location": "24370", "jurisdiction": "Smyth County", "needs": ["housing"],
           "circumstances": ["displaced"], "context_reviewed": True}


@pytest.mark.parametrize("method,path,body", [
    ("GET", "/api/surge/status", None),
    ("POST", "/api/navigate", PROFILE),
    ("POST", "/api/transform", {"language": "en"}),
])
def test_endpoints_survive_host_without_middleware_state(monkeypatch, method, path, body):
    # Route directly through ASGI without the HTTP middleware: neither state nor
    # last_mile_surge is populated. This exercises the host fallback at endpoints.
    monkeypatch.setenv("SURGE_MODE", "true")
    client = TestClient(AsyncExitStackMiddleware(app.router))
    response = client.request(method, path, json=body) if body else client.get(path)
    assert response.status_code == 200
    result = response.json()
    if path.endswith("status"):
        assert result["active"] and result["mode"] == "surge"
    elif path.endswith("navigate"):
        assert result["surge"]["active"] and result["recommendations"]
    else:
        assert result["provider_mode"] == "surge-deterministic" and result["segments"]


def test_freshness_conflict_replay_and_surge_contracts():
    client = TestClient(app)
    response = client.get("/api/programs/freshness")
    assert response.status_code == 200
    body = response.json()
    assert body["records"]
    assert body["stale_count"] == sum(row["stale"] for row in body["records"])
    assert all(
        {"id", "reasons", "reason_codes", "review_interval_days", "last_verified", "as_of"}
        <= row.keys()
        for row in body["records"]
    )
    conflicts = client.get("/api/source-conflicts")
    assert conflicts.status_code == 200
    assert conflicts.json() == {"conflict_detected": False, "conflicts": [], "action": "continue"}
    replay = client.get("/api/scenarios/replay")
    assert replay.status_code == 200 and replay.json()["failed"] == 0
    assert replay.json()["passed"] == replay.json()["scenario_count"] > 0
    surge = client.get("/api/surge/status")
    assert surge.status_code == 200
    assert surge.json()["mode"] in {"normal", "surge"}
    assert surge.headers["x-last-mile-mode"] in {"normal", "surge"}


def test_chaos_unknown_modes_are_ignored():
    response = TestClient(app).post("/api/chaos/evaluate", json={"modes": ["foundry_down", "arbitrary_code"]})
    assert response.status_code == 200
    body = response.json()
    assert body["simulated"] is True
    assert body["modes"] == ["foundry_down"]
    assert body["outcomes"][0]["fallback"] == "deterministic rules + reviewed copy"


def test_saved_packet_diff_snapshot_and_preferences():
    client = TestClient(app)
    response = client.post("/api/packet", json={**PROFILE, "accessibility_preferences": ["relay_service", "unknown"]})
    assert response.status_code == 200
    packet = response.json()["packet"]
    assert packet["accessibility"]["preferences"] == ["relay_service"]
    code = packet["continuity"]["code"]
    diff = client.get(f"/api/packet/diff/{code}")
    assert diff.status_code == 200 and diff.json()["changed"] is False and diff.json()["changes"] == []
    response = client.get(f"/api/packet/offline/{code}")
    assert response.status_code == 200 and "attachment" in response.headers["content-disposition"]
    snapshot = response.json()
    assert snapshot["format"] == "last-mile-offline-snapshot-v1"
    assert snapshot["packet"] == packet
    verified = client.post("/api/offline/verify", json={"snapshot": snapshot})
    assert verified.status_code == 200 and verified.json()["valid"] is True
    damaged = deepcopy(snapshot)
    damaged["packet"]["jurisdiction"] = "Wrong County"
    assert client.post("/api/offline/verify", json={"snapshot": damaged}).json()["valid"] is False


@pytest.mark.parametrize("path", ["/api/continue/", "/api/packet/diff/", "/api/packet/offline/", "/api/handoff/"])
@pytest.mark.parametrize("expired", [False, True])
def test_unknown_or_expired_codes_return_bounded_404(monkeypatch, path, expired):
    if expired:
        # Stores share the contract of returning None after expiry; storage expiry
        # itself is covered separately by continuity-store tests.
        monkeypatch.setattr("api.main.continuity_store.load", lambda code: None)
    response = TestClient(app).get(path + "RBX-NOPE0")
    assert response.status_code == 404
    assert response.json() == {"detail": "Recovery code not found or expired"}


@pytest.mark.parametrize("snapshot", [{}, {"packet": []}, {"packet": {"proof": []}},
                                      {"packet": {"deadlines": []}}, {"packet": {"channels": []}}])
def test_malformed_snapshots_return_bounded_400(snapshot):
    response = TestClient(app, raise_server_exceptions=False).post("/api/offline/verify", json={"snapshot": snapshot})
    assert response.status_code == 400
    assert len(response.content) < 200 and set(response.json()) == {"detail"}
