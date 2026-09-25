from types import SimpleNamespace

from fastapi.testclient import TestClient

import api.main as main_module
import api.providers.azure_voice as voice_module
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


def test_call_start_requires_explicit_consent():
    payload = packet()
    response = client.post(
        "/api/calls/start",
        json={
            "continuity_code": payload["continuity"]["code"],
            "phone_number": "+17035550123",
            "consent": False,
        },
    )
    assert response.status_code == 400
    assert "consent" in response.json()["detail"].lower()


def test_call_start_endpoint_uses_verified_continuity_packet(monkeypatch):
    payload = packet()

    def fake_start(phone_number, supplied_packet, consent):
        assert phone_number == "+17035550123"
        assert supplied_packet["proof"]["proof_id"] == payload["proof"]["proof_id"]
        assert consent is True
        return {
            "status": "accepted",
            "call_connection_id": "call-1",
            "proof_id": supplied_packet["proof"]["proof_id"],
        }

    monkeypatch.setattr(main_module, "start_verified_call", fake_start)
    response = client.post(
        "/api/calls/start",
        json={
            "continuity_code": payload["continuity"]["code"],
            "phone_number": "+17035550123",
            "consent": True,
        },
    )
    assert response.status_code == 200
    assert response.json()["call_connection_id"] == "call-1"


def test_provider_starts_call_with_signed_callback_and_neural_voice(monkeypatch):
    payload = packet()
    observed = {}

    class FakeClient:
        def create_call(self, **kwargs):
            observed.update(kwargs)
            return SimpleNamespace(call_connection_id="provider-call")

    fake_settings = SimpleNamespace(
        call_enabled=True,
        call_allowed_test_recipients=("+17035550123",),
        call_from_number="+18005550123",
        call_cognitive_endpoint="https://example.cognitiveservices.azure.com",
        call_voice_name="en-US-JennyNeural",
        call_source_locale="en-US",
        public_base_url="https://navigator.example",
        manifest_signing_key="test-signing-key",
        communication_connection_string="",
        communication_endpoint="https://example.communication.azure.com",
    )
    monkeypatch.setattr(voice_module, "settings", fake_settings)
    monkeypatch.setattr(voice_module, "_client", lambda: FakeClient())

    result = voice_module.start_verified_call("+17035550123", payload, True)

    assert result["call_connection_id"] == "provider-call"
    assert observed["callback_url"].startswith(
        f"https://navigator.example/api/calls/events/{payload['continuity']['code']}?sig="
    )
    assert observed["cognitive_services_endpoint"] == fake_settings.call_cognitive_endpoint
    assert observed["operation_context"] == payload["proof"]["proof_id"]


def test_callback_rejects_invalid_signature():
    payload = packet()
    response = client.post(
        f"/api/calls/events/{payload['continuity']['code']}?sig=wrong",
        json=[{"type": "Microsoft.Communication.CallConnected", "data": {}}],
    )
    assert response.status_code == 400
    assert "signature" in response.json()["detail"].lower()


def test_dtmf_human_help_plays_safety_prompt_then_hangs_up(monkeypatch):
    payload = packet()
    actions = []

    class FakeConnection:
        def play_media_to_all(self, source, **kwargs):
            actions.append(("play", source.text, kwargs.get("operation_context")))

        def hang_up(self, **kwargs):
            actions.append(("hangup", kwargs["is_for_everyone"]))

    fake_connection = FakeConnection()

    class FakeClient:
        def get_call_connection(self, connection_id):
            assert connection_id == "call-1"
            return fake_connection

    fake_settings = SimpleNamespace(
        manifest_signing_key="local-demo-key-not-for-production",
        call_voice_name="en-US-JennyNeural",
        call_source_locale="en-US",
    )
    monkeypatch.setattr(voice_module, "settings", fake_settings)
    monkeypatch.setattr(voice_module, "_client", lambda: FakeClient())
    signature = voice_module._callback_signature(payload["continuity"]["code"])

    recognized = voice_module.handle_call_events(
        payload["continuity"]["code"],
        signature,
        [
            {
                "type": "Microsoft.Communication.RecognizeCompleted",
                "data": {
                    "callConnectionId": "call-1",
                    "dtmfResult": {"tones": ["zero"]},
                },
            }
        ],
    )
    assert recognized["events"][0]["action"] == "human_help_then_hangup"
    assert "Virginia 2 1 1" in actions[0][1]
    assert actions[0][2] == "last-mile-hangup"

    completed = voice_module.handle_call_events(
        payload["continuity"]["code"],
        signature,
        [
            {
                "type": "Microsoft.Communication.PlayCompleted",
                "data": {
                    "callConnectionId": "call-1",
                    "operationContext": "last-mile-hangup",
                },
            }
        ],
    )
    assert completed["events"][0]["action"] == "call_ended"
    assert actions[-1] == ("hangup", True)


def test_voice_opening_is_short_and_puts_choices_before_case_details():
    opening = voice_module._opening_text()

    assert "automated disaster assistance demo" in opening
    assert "immediate danger" in opening
    assert "Press 1" in opening
    assert "DR-4831-VA" not in opening
    assert "November 18" not in opening
    assert len(opening.split()) < 60


def test_key_nine_repeats_without_error_message():
    response, should_hang_up = voice_module._response_for_tone("9", packet())

    assert response == "Here are the choices again."
    assert should_hang_up is False
    assert "not recognize" not in response.lower()


def test_pound_key_explains_the_demo_and_returns_to_menu():
    payload = packet()
    response, should_hang_up = voice_module._response_for_tone("#", payload)

    assert "one signed disaster plan" in response
    assert "locked government facts" in response
    assert "without a name or account" in response
    assert should_hang_up is False


def test_azure_pound_tone_maps_to_demo_option():
    assert voice_module._tone({"dtmfResult": {"tones": ["pound"]}}) == "#"
    assert voice_module._tone({"dtmfResult": {"tones": ["DtmfTone.POUND"]}}) == "#"


def test_next_steps_explain_historical_limit_and_spell_recovery_code():
    payload = packet()
    response, should_hang_up = voice_module._response_for_tone("1", payload)

    assert payload["jurisdiction"] in response
    assert "historical disaster example" in response
    assert "deadline" in response
    assert ", ".join(payload["continuity"]["code"].replace("-", "")) in response
    assert should_hang_up is False


def test_missing_documents_key_protects_sensitive_information_and_returns_to_menu():
    response, should_hang_up = voice_module._response_for_tone("2", packet())

    assert "do not send sensitive information" in response
    assert "alternative documents" in response
    assert "Press 0" in response
    assert should_hang_up is False


def test_unknown_key_reprompts_with_only_supported_choices():
    response, should_hang_up = voice_module._response_for_tone("7", packet())

    assert "not an option" in response
    for choice in ("1", "2", "pound", "0", "9"):
        assert choice in response
    assert should_hang_up is False
