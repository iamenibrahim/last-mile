from types import SimpleNamespace

from fastapi.testclient import TestClient

import api.main as main_module
import api.providers.azure_sms as sms_module
from api.main import app
from api.protocol import build_action_packet


client = TestClient(app)
PROFILE = {
    "location": "24370",
    "jurisdiction": "Smyth County",
    "needs": ["home_repair", "housing", "documents"],
    "circumstances": ["displaced", "no_id"],
    "context_reviewed": True,
}


def packet():
    return build_action_packet(PROFILE)["packet"]


def test_sms_send_requires_explicit_consent():
    payload = packet()
    response = client.post(
        "/api/sms/send",
        json={
            "continuity_code": payload["continuity"]["code"],
            "phone_number": "+15715550123",
            "consent": False,
        },
    )
    assert response.status_code == 400
    assert "consent" in response.json()["detail"].lower()


def test_sms_send_endpoint_uses_verified_continuity_packet(monkeypatch):
    payload = packet()

    def fake_send(phone_number, supplied_packet, consent):
        assert phone_number == "+15715550123"
        assert supplied_packet["proof"]["proof_id"] == payload["proof"]["proof_id"]
        assert consent is True
        return {
            "status": "accepted",
            "successful": True,
            "message_id": "test-message",
            "proof_id": supplied_packet["proof"]["proof_id"],
        }

    monkeypatch.setattr(main_module, "send_verified_packet", fake_send)
    response = client.post(
        "/api/sms/send",
        json={
            "continuity_code": payload["continuity"]["code"],
            "phone_number": "+15715550123",
            "consent": True,
        },
    )
    assert response.status_code == 200
    assert response.json()["successful"] is True


def test_sms_provider_sends_only_verified_compiled_text(monkeypatch):
    payload = packet()
    sent = {}

    class FakeClient:
        def send(self, **kwargs):
            sent.update(kwargs)
            return [
                SimpleNamespace(
                    successful=True,
                    message_id="provider-message",
                    http_status_code=202,
                    error_message=None,
                )
            ]

    fake_settings = SimpleNamespace(
        sms_enabled=True,
        sms_allowed_test_recipients=("+15715550123",),
        sms_from_number="+18005550123",
        communication_connection_string="",
        communication_endpoint="https://example.communication.azure.com",
        sms_auto_reply_enabled=False,
    )
    monkeypatch.setattr(sms_module, "settings", fake_settings)
    monkeypatch.setattr(sms_module, "_client", lambda: FakeClient())
    result = sms_module.send_verified_packet("+15715550123", payload, True)
    assert result["successful"] is True
    assert sent["message"] == payload["channels"]["sms"]["text"]
    assert sent["tag"] == payload["proof"]["proof_id"]
    assert sent["enable_delivery_report"] is True


def test_event_grid_validation_and_delivery_report_are_supported():
    validation = client.post(
        "/api/sms/events",
        json=[
            {
                "eventType": "Microsoft.EventGrid.SubscriptionValidationEvent",
                "data": {"validationCode": "abc123"},
            }
        ],
    )
    assert validation.status_code == 200
    assert validation.json() == {"validationResponse": "abc123"}

    report = client.post(
        "/api/sms/events",
        json=[
            {
                "eventType": "Microsoft.Communication.SMSDeliveryReportReceived",
                "data": {
                    "messageId": "message-1",
                    "deliveryStatus": "Delivered",
                    "to": "+15715550123",
                },
            }
        ],
    )
    assert report.status_code == 200
    body = report.json()
    assert body["events"][0]["delivery_status"] == "Delivered"
    assert "+15715550123" not in str(body)


def test_inbound_recovery_command_returns_stateless_reply_preview():
    payload = packet()
    response = client.post(
        "/api/sms/events",
        json=[
            {
                "eventType": "Microsoft.Communication.SMSReceived",
                "data": {
                    "from": "+15715550123",
                    "to": "+18005550123",
                    "message": f"CONTINUE {payload['continuity']['code']}",
                },
            }
        ],
    )
    assert response.status_code == 200
    event = response.json()["events"][0]
    assert event["recognized"] is True
    assert payload["continuity"]["code"] in event["reply_preview"]
    assert "+15715550123" not in str(event)
