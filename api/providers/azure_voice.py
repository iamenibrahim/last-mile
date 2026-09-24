from __future__ import annotations

import hashlib
import hmac
import re
from typing import Any
from urllib.parse import quote

from ..config import settings
from ..protocol import continuity_store, verify_action_packet


E164 = re.compile(r"^\+[1-9]\d{7,14}$")
TONE_NAMES = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "nine": "9",
    "0": "0",
    "1": "1",
    "2": "2",
    "9": "9",
}


def _client():
    from azure.communication.callautomation import CallAutomationClient  # type: ignore

    if settings.communication_connection_string:
        return CallAutomationClient.from_connection_string(
            settings.communication_connection_string
        )

    from azure.identity import DefaultAzureCredential  # type: ignore

    return CallAutomationClient(
        settings.communication_endpoint,
        DefaultAzureCredential(),
    )


def _validate_recipient(phone_number: str) -> str:
    number = phone_number.strip()
    if not E164.fullmatch(number):
        raise ValueError("Use E.164 format, for example +17035550123")
    if settings.call_allowed_test_recipients and number not in settings.call_allowed_test_recipients:
        raise ValueError("This number is not on the student-pilot call allowlist")
    return number


def _callback_signature(continuity_code: str) -> str:
    return hmac.new(
        settings.manifest_signing_key.encode("utf-8"),
        f"acs-call:{continuity_code}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _callback_url(continuity_code: str) -> str:
    base = settings.public_base_url.rstrip("/")
    signature = _callback_signature(continuity_code)
    return f"{base}/api/calls/events/{quote(continuity_code)}?sig={signature}"


def start_verified_call(
    phone_number: str,
    packet: dict[str, Any],
    consent: bool,
) -> dict[str, Any]:
    if consent is not True:
        raise ValueError("Explicit consent to one automated voice call is required")
    verification = verify_action_packet(packet)
    if not verification["valid"]:
        raise ValueError("Packet signature, channel hash, or locked facts did not verify")
    if not settings.call_enabled:
        raise RuntimeError("Azure automated calling is not enabled")

    recipient = _validate_recipient(phone_number)
    from azure.communication.callautomation import PhoneNumberIdentifier  # type: ignore

    result = _client().create_call(
        target_participant=PhoneNumberIdentifier(recipient),
        callback_url=_callback_url(packet["continuity"]["code"]),
        source_caller_id_number=PhoneNumberIdentifier(settings.call_from_number),
        cognitive_services_endpoint=settings.call_cognitive_endpoint,
        operation_context=packet["proof"]["proof_id"],
    )
    return {
        "status": "accepted",
        "call_connection_id": result.call_connection_id,
        "proof_id": packet["proof"]["proof_id"],
        "transport": "azure_communication_services_call_automation",
        "voice": settings.call_voice_name,
    }


def _text_source(text: str):
    from azure.communication.callautomation import TextSource  # type: ignore

    return TextSource(
        text=text[:3000],
        source_locale=settings.call_source_locale,
        voice_name=settings.call_voice_name,
    )


def _external_participant(call_connection):
    """Find the PSTN participant without persisting or returning the phone number."""

    participants = call_connection.list_participants()
    for participant in participants:
        identifier = getattr(participant, "identifier", None)
        properties = getattr(identifier, "properties", {}) or {}
        value = properties.get("value") if isinstance(properties, dict) else None
        if value and value != settings.call_from_number:
            return identifier
    raise RuntimeError("The external call participant is unavailable")


def _menu_choices() -> str:
    # Short, parallel phrases are easier to retain over a noisy phone line than
    # a long explanation followed by four choices.
    return (
        "Press 1 for your next steps. "
        "Press 2 for help with missing documents. "
        "Press 0 for human help. "
        "Press 9 to repeat these choices."
    )


def _opening_text() -> str:
    return (
        "Hello. This is Last Mile, an automated disaster assistance demo. "
        "If you are in immediate danger, hang up and call 911. "
        "Choose one option now. "
        f"{_menu_choices()}"
    )


def _spoken_code(code: str) -> str:
    return ", ".join(code.replace("-", ""))


def _tone(event_data: dict[str, Any]) -> str | None:
    result = event_data.get("dtmfResult") or event_data.get("recognitionResult") or {}
    tones = result.get("tones", []) if isinstance(result, dict) else []
    if not tones:
        return None
    raw = str(tones[0]).split(".")[-1].lower()
    return TONE_NAMES.get(raw)


def _response_for_tone(tone: str | None, packet: dict[str, Any]) -> tuple[str, bool]:
    if tone == "1":
        actions = " ".join(
            f"Step {index + 1}. {action['label']}"
            for index, action in enumerate(packet["actions"][:3])
        )
        return (
            f"This plan is for {packet['jurisdiction']}. "
            "It uses a historical disaster example, and the application deadline in that example has passed. "
            f"{actions} "
            f"Your recovery code is {_spoken_code(packet['continuity']['code'])}.",
            False,
        )
    if tone == "2":
        return (
            "If identification or other documents were lost, do not send sensitive information yet. "
            "Ask the agency which alternative documents it accepts. "
            "Press 0 if you want human help.",
            False,
        )
    if tone == "0":
        return (
            "For a human navigator, call Virginia 2 1 1. Use 7 1 1 for relay services. "
            "If anyone is in immediate danger, hang up and call 911 now.",
            True,
        )
    if tone == "9":
        return "Here are the choices again.", False
    return "That key is not an option. Please choose 1, 2, 0, or 9.", False


def _start_menu(
    call_connection,
    packet: dict[str, Any],
    prefix: str = "",
    *,
    opening: bool = False,
) -> None:
    from azure.communication.callautomation import RecognizeInputType  # type: ignore

    target = _external_participant(call_connection)
    menu = _opening_text() if opening else _menu_choices()
    prompt = f"{prefix} {menu}".strip()
    call_connection.start_recognizing_media(
        input_type=RecognizeInputType.DTMF,
        target_participant=target,
        play_prompt=_text_source(prompt),
        interrupt_prompt=True,
        interrupt_call_media_operation=True,
        dtmf_max_tones_to_collect=1,
        dtmf_inter_tone_timeout=5,
        operation_context="last-mile-menu",
    )


def handle_call_events(
    continuity_code: str,
    signature: str,
    events: list[dict[str, Any]] | dict[str, Any],
) -> dict[str, Any]:
    if not hmac.compare_digest(signature or "", _callback_signature(continuity_code)):
        raise ValueError("Invalid call callback signature")
    packet = continuity_store.load(continuity_code)
    if not packet or not verify_action_packet(packet)["valid"]:
        raise ValueError("Recovery code is invalid or expired")

    normalized = events if isinstance(events, list) else [events]
    outcomes: list[dict[str, Any]] = []
    client = _client()

    for event in normalized:
        event_type = str(event.get("type") or event.get("eventType") or "")
        data = event.get("data") or {}
        connection_id = data.get("callConnectionId")
        short_type = event_type.rsplit(".", 1)[-1]
        outcome: dict[str, Any] = {"event": short_type or "unknown"}

        if not connection_id:
            outcomes.append(outcome)
            continue

        call_connection = client.get_call_connection(connection_id)
        if short_type == "CallConnected":
            _start_menu(call_connection, packet, opening=True)
            outcome["action"] = "menu_started"
        elif short_type == "RecognizeCompleted":
            tone = _tone(data)
            response, should_hang_up = _response_for_tone(tone, packet)
            if should_hang_up:
                call_connection.play_media_to_all(
                    _text_source(response),
                    operation_context="last-mile-hangup",
                    interrupt_call_media_operation=True,
                )
                outcome["action"] = "human_help_then_hangup"
            else:
                _start_menu(call_connection, packet, response)
                outcome["action"] = "menu_continued"
            outcome["selection"] = tone
        elif short_type == "RecognizeFailed":
            _start_menu(call_connection, packet, "I did not hear a key. Let's try again.")
            outcome["action"] = "menu_retried"
        elif short_type == "PlayCompleted" and data.get("operationContext") == "last-mile-hangup":
            call_connection.hang_up(is_for_everyone=True)
            outcome["action"] = "call_ended"
        elif short_type in {"CallDisconnected", "PlayFailed"}:
            outcome["action"] = "no_follow_up"
        outcomes.append(outcome)

    return {"status": "accepted", "events": outcomes}
