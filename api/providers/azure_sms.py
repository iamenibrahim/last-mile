from __future__ import annotations

import re
from typing import Any

from ..config import settings
from ..protocol import continuity_store, verify_action_packet


E164 = re.compile(r"^\+[1-9]\d{7,14}$")
CONTINUE = re.compile(r"\b(?:CONTINUE\s+)?(RBX-[A-Z0-9]{5,12})(?:\s+([012]))?\b", re.I)


def _client():
    from azure.communication.sms import SmsClient  # type: ignore

    if settings.communication_connection_string:
        return SmsClient.from_connection_string(settings.communication_connection_string)

    from azure.identity import DefaultAzureCredential  # type: ignore

    return SmsClient(settings.communication_endpoint, DefaultAzureCredential())


def _validate_recipient(phone_number: str) -> str:
    number = phone_number.strip()
    if not E164.fullmatch(number):
        raise ValueError("Use E.164 format, for example +15715550123")
    if settings.sms_allowed_test_recipients and number not in settings.sms_allowed_test_recipients:
        raise ValueError("This number is not on the student-pilot recipient allowlist")
    return number


def send_text(phone_number: str, message: str, proof_id: str) -> dict[str, Any]:
    if not settings.sms_enabled:
        raise RuntimeError("Azure SMS delivery is not enabled")
    recipient = _validate_recipient(phone_number)
    if not message or len(message) > 320:
        raise ValueError("Verified SMS text must contain 1 to 320 characters")

    results = _client().send(
        from_=settings.sms_from_number,
        to=recipient,
        message=message,
        enable_delivery_report=True,
        tag=proof_id,
    )
    result = results[0]
    return {
        "status": "accepted" if result.successful else "failed",
        "successful": bool(result.successful),
        "message_id": result.message_id,
        "http_status_code": result.http_status_code,
        "error": result.error_message,
        "proof_id": proof_id,
        "transport": "azure_communication_services",
    }


def send_verified_packet(phone_number: str, packet: dict, consent: bool) -> dict[str, Any]:
    if consent is not True:
        raise ValueError("Explicit SMS consent is required")
    verification = verify_action_packet(packet)
    if not verification["valid"]:
        raise ValueError("Packet signature, channel hash, or locked facts did not verify")
    return send_text(
        phone_number,
        packet["channels"]["sms"]["text"],
        packet["proof"]["proof_id"],
    )


def _reply_for_command(message: str) -> tuple[str | None, str | None]:
    match = CONTINUE.search(message.strip().upper())
    if not match:
        return None, None
    code, command = match.group(1).upper(), match.group(2)
    packet = continuity_store.load(code)
    if not packet or not verify_action_packet(packet)["valid"]:
        return code, "That Last-Mile recovery code is invalid or expired. Call Virginia 211 for help."
    if command == "1":
        steps = " ".join(
            f"{index + 1}) {action['label']}" for index, action in enumerate(packet["actions"][:3])
        )
        return code, f"{steps} Proof {packet['proof']['proof_id']}."
    if command == "2":
        return code, (
            "If documents were lost, ask the agency which identity alternatives it accepts before "
            f"sending anything. Proof {packet['proof']['proof_id']}."
        )
    if command == "0":
        return code, "Call Virginia 211 for a navigator, 711 for relay, or 911 for immediate danger."
    return code, (
        f"Last-Mile {code}: reply '{code} 1' for steps, '{code} 2' for document alternatives, "
        f"or '{code} 0' for human help."
    )


def handle_event_grid_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    outcomes: list[dict[str, Any]] = []
    for event in events:
        event_type = event.get("eventType") or event.get("type")
        data = event.get("data", {})
        if event_type == "Microsoft.EventGrid.SubscriptionValidationEvent":
            return {"validationResponse": data.get("validationCode", "")}
        if event_type == "Microsoft.Communication.SMSDeliveryReportReceived":
            outcomes.append(
                {
                    "event": "delivery_report",
                    "message_id": data.get("messageId"),
                    "delivery_status": data.get("deliveryStatus"),
                }
            )
            continue
        if event_type == "Microsoft.Communication.SMSReceived":
            code, reply = _reply_for_command(str(data.get("message", "")))
            outcome: dict[str, Any] = {"event": "sms_received", "recognized": bool(reply), "code": code}
            if reply and settings.sms_auto_reply_enabled:
                send_result = send_text(str(data.get("from", "")), reply[:320], f"reply-{code or 'help'}")
                outcome["reply"] = send_result
            elif reply:
                outcome["reply_preview"] = reply[:320]
            outcomes.append(outcome)
    return {"status": "accepted", "events": outcomes}
