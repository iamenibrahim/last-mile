from __future__ import annotations

import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .config import settings


ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = ROOT / "data" / "cached_alerts" / "hampton_roads_flood.json"


def canonicalize(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def payload_hash(payload: dict) -> str:
    return hashlib.sha256(canonicalize(payload).encode("utf-8")).hexdigest()


def load_cached_alert() -> dict:
    return json.loads(CACHE_PATH.read_text(encoding="utf-8"))


def fetch_active_va_alerts() -> dict:
    request = urllib.request.Request(
        "https://api.weather.gov/alerts/active?area=VA",
        headers={"User-Agent": settings.nws_user_agent, "Accept": "application/geo+json"},
    )
    # The request uses the fixed HTTPS NWS endpoint declared above.
    with urllib.request.urlopen(request, timeout=8) as response:  # nosec B310
        payload = json.load(response)
    return {
        "features": payload.get("features", []),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "transport": "TLS to api.weather.gov",
        "mode": "live",
    }


def alerts_with_fallback() -> dict:
    try:
        live = fetch_active_va_alerts()
        if live["features"]:
            return live
    except Exception:
        pass
    cached = load_cached_alert()
    return {
        "features": [cached],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "transport": "local verified demo fixture",
        "mode": "cached",
    }
