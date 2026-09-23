from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import settings
from .fraud import scan_message
from .geo import classify_position, geocode
from .ingest import alerts_with_fallback, load_cached_alert
from .manifest import validate_manifest
from .navigator import navigate
from .providers.azure_sms import handle_event_grid_events, send_verified_packet
from .providers.azure_voice import handle_call_events, start_verified_call
from .protocol import build_action_packet, continuity_store, next_question, verify_action_packet
from .speech import synthesize
from .store import create_store
from .transform import LANGUAGES, transform_alert
from grounded.main import _startup as grounded_startup, app as grounded_app


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
DATA = ROOT / "data"

app = FastAPI(
    title="Last-Mile Navigator API",
    version="1.0.0",
    description="Grounded disaster-assistance navigation with per-segment abstention and provenance.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
render_store = create_store()


class NavigateRequest(BaseModel):
    location: str = Field(default="Norfolk, VA", max_length=200)
    urgency: str = "safe_now"
    needs: list[str] = Field(default_factory=list, max_length=20)
    circumstances: list[str] = Field(default_factory=list, max_length=20)
    household: str | None = None
    housing: str | None = None
    jurisdiction: str | None = None
    context_reviewed: bool | None = None


class TransformRequest(BaseModel):
    language: str = "es"
    grade: int = Field(default=6, ge=4, le=10)
    simulate_failure: bool = False
    alert: dict[str, Any] | None = None


class VerifyRequest(BaseModel):
    manifest: dict[str, Any]
    rendered_text: str | None = None


class FraudRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10000)


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=3000)
    language: str = "en"


class PacketRequest(BaseModel):
    location: str = Field(default="24370", max_length=200)
    jurisdiction: str | None = None
    needs: list[str] = Field(default_factory=list, max_length=20)
    circumstances: list[str] = Field(default_factory=list, max_length=20)
    context_reviewed: bool | None = None


class PacketVerifyRequest(BaseModel):
    packet: dict[str, Any]


class SmsSendRequest(BaseModel):
    continuity_code: str = Field(pattern=r"^RBX-[A-Z0-9]{5,12}$")
    phone_number: str = Field(min_length=8, max_length=16)
    consent: bool = False


class CallStartRequest(BaseModel):
    continuity_code: str = Field(pattern=r"^RBX-[A-Z0-9]{5,12}$")
    phone_number: str = Field(min_length=8, max_length=16)
    consent: bool = False


@app.get("/api/status")
def status() -> dict:
    return {
        "status": "ready",
        "mode": settings.environment,
        "providers": {
            "microsoft_foundry": settings.foundry_enabled,
            "azure_ai_translator": settings.translator_enabled,
            "azure_ai_speech": settings.speech_enabled,
            "azure_ai_content_safety": settings.content_safety_enabled,
            "azure_maps": bool(settings.azure_maps_key),
            "cosmos_db": bool(settings.cosmos_endpoint),
            "azure_communication_services_sms": settings.sms_enabled,
            "azure_communication_services_voice": settings.call_enabled,
        },
        "fallback": "Every cloud provider has a deterministic or cached local path.",
        "languages": LANGUAGES,
    }


@app.get("/api/config")
def public_config() -> dict:
    return {
        "azure_maps_key": settings.azure_maps_key,
        "environment": settings.environment,
        "demo_location": {"latitude": 36.8508, "longitude": -76.2859},
    }


@app.get("/api/alerts")
def alerts() -> dict:
    return alerts_with_fallback()


@app.post("/api/navigate")
def navigation(request: NavigateRequest) -> dict:
    result = navigate(request.model_dump())
    alert = load_cached_alert()
    location = geocode(request.location)
    point = location.pop("point")
    result["location_match"] = {**location, "latitude": point.latitude, "longitude": point.longitude}
    result["alert_context"] = {
        "alert": alert,
        "position": classify_position(point, alert.get("geometry")),
    }
    result["protocol"] = build_action_packet(request.model_dump())
    if result["protocol"].get("status") == "complete":
        result["privacy"].update(
            {
                "stored": True,
                "retention": "24 hours",
                "stored_fields": ["county", "disaster ID", "broad needs", "constraints", "current step"],
                "message": (
                    "The full screening response is not logged. To make the anonymous recovery code work, "
                    "a minimal action packet is retained for 24 hours."
                ),
            }
        )
    return result


@app.post("/api/intake/next")
def intake_next(request: PacketRequest) -> dict:
    return next_question(request.model_dump(exclude_none=True))


@app.post("/api/packet")
def action_packet(request: PacketRequest) -> dict:
    return build_action_packet(request.model_dump(exclude_none=True))


@app.post("/api/packet/verify")
def action_packet_verify(request: PacketVerifyRequest) -> dict:
    return verify_action_packet(request.packet)


@app.get("/api/continue/{code}")
def continue_packet(code: str) -> dict:
    packet = continuity_store.load(code)
    if not packet:
        raise HTTPException(status_code=404, detail="Recovery code not found or expired")
    return {"status": "complete", "packet": packet, "resumed": True}


@app.get("/api/handoff/{code}")
def caseworker_handoff(code: str) -> dict:
    """Flat, read-only summary of a stored packet for a Copilot Studio caseworker agent.

    Every field is copied from the signed packet; nothing is generated here, and the
    packet signature is re-checked so the agent can refuse a packet that fails it.
    """
    packet = continuity_store.load(code)
    if not packet:
        raise HTTPException(status_code=404, detail="Recovery code not found or expired")
    sources = {source["id"]: source for source in packet.get("sources", [])}
    escalation = packet.get("escalation", {})
    return {
        "code": packet["continuity"]["code"],
        "packet_id": packet.get("packet_id"),
        "packet_verified": verify_action_packet(packet)["valid"],
        "jurisdiction": packet.get("jurisdiction"),
        "disaster_id": packet.get("disaster", {}).get("id"),
        "disaster_name": packet.get("disaster", {}).get("name"),
        "snapshot_notice": packet.get("snapshot", {}).get("notice"),
        "needs": packet.get("needs", []),
        "constraints": packet.get("constraints", []),
        "escalation_required": bool(escalation.get("required")),
        "escalation_topic": escalation.get("topic"),
        "contact": escalation.get("contact"),
        "caller_summary": escalation.get("read_this"),
        "deadlines": [
            {
                "display": deadline.get("display"),
                "status": deadline.get("current_status"),
                "source_url": sources.get(deadline.get("source_id"), {}).get("url"),
            }
            for deadline in packet.get("deadlines", [])
        ],
        "actions": [
            {
                "priority": action.get("priority"),
                "label": action.get("label"),
                "confidence": action.get("confidence"),
                "current_limit": action.get("current_limit"),
                "source_url": sources.get(action.get("source_id"), {}).get("url"),
            }
            for action in packet.get("actions", [])
        ],
        "boundary": "This summary does not decide eligibility. The agency decides.",
    }


@app.post("/api/sms/send")
def sms_send(request: SmsSendRequest) -> dict:
    packet = continuity_store.load(request.continuity_code)
    if not packet:
        raise HTTPException(status_code=404, detail="Recovery code not found or expired")
    try:
        return send_verified_packet(request.phone_number, packet, request.consent)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"SMS provider unavailable: {type(error).__name__}")


@app.post("/api/sms/events")
def sms_events(events: list[dict[str, Any]]) -> dict:
    return handle_event_grid_events(events)


@app.post("/api/calls/start")
def call_start(request: CallStartRequest) -> dict:
    packet = continuity_store.load(request.continuity_code)
    if not packet:
        raise HTTPException(status_code=404, detail="Recovery code not found or expired")
    try:
        return start_verified_call(request.phone_number, packet, request.consent)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Call provider unavailable: {type(error).__name__}")


@app.post("/api/calls/events/{continuity_code}")
def call_events(
    continuity_code: str,
    events: list[dict[str, Any]] | dict[str, Any],
    sig: str = "",
) -> dict:
    try:
        return handle_call_events(continuity_code, sig, events)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


@app.post("/api/transform")
def transform(request: TransformRequest) -> dict:
    if request.language not in LANGUAGES:
        raise HTTPException(status_code=400, detail="Unsupported demo language")
    alert = request.alert or load_cached_alert()
    result = transform_alert(alert, request.language, request.grade, request.simulate_failure)
    try:
        render_store.save_render(result)
    except Exception:
        result["cache_notice"] = "Render cache unavailable; the verified response is still shown."
    return result


@app.post("/api/verify")
def verify(request: VerifyRequest) -> dict:
    result = validate_manifest(request.manifest, request.rendered_text)
    result["source"] = request.manifest.get("source")
    result["segments"] = request.manifest.get("segments", [])
    return result


@app.post("/api/fraud-check")
def fraud_check(request: FraudRequest) -> dict:
    return scan_message(request.text)


@app.post("/api/speech")
def speech(request: SpeechRequest) -> Response:
    try:
        audio = synthesize(request.text, request.language)
    except RuntimeError as error:
        return JSONResponse(
            status_code=503,
            content={
                "detail": str(error),
                "fallback": "Use the device speech-synthesis button; no text leaves the browser.",
            },
        )
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Speech provider unavailable: {type(error).__name__}")
    return Response(audio, media_type="audio/mpeg")


@app.get("/api/evaluation")
def evaluation() -> dict:
    path = DATA / "evaluation_report.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"status": "not_run", "notice": "Run python -m eval.report before quoting metrics."}


@app.get("/healthz")
def health() -> dict:
    return {"ok": True}


app.mount("/assets", StaticFiles(directory=WEB), name="assets")

# The real-data evidence pipeline: 80 cached NWS alerts, hash-verified FEMA/eCFR/
# SBA/SAMHSA quotes, and OpenFEMA deadline rules. Mounted before the SPA
# catch-all so /grounded/... reaches it. Mounted apps do not get startup events,
# so its alert store is loaded here.
app.mount("/grounded", grounded_app)


@app.on_event("startup")
def _load_grounded_corpus() -> None:
    grounded_startup()


@app.get("/{path:path}")
def spa(path: str) -> FileResponse:
    candidate = WEB / path
    if path and candidate.is_file() and WEB in candidate.resolve().parents:
        return FileResponse(candidate)
    return FileResponse(WEB / "index.html")
