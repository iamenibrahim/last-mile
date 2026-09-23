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
from .protocol import build_action_packet, continuity_store, next_question, verify_action_packet
from .speech import synthesize
from .store import create_store
from .transform import LANGUAGES, transform_alert


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


@app.get("/{path:path}")
def spa(path: str) -> FileResponse:
    candidate = WEB / path
    if path and candidate.is_file() and WEB in candidate.resolve().parents:
        return FileResponse(candidate)
    return FileResponse(WEB / "index.html")
