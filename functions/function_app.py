"""Azure Functions timer trigger for NWS ingest.

The function stores only alert material. It does not receive or persist citizen
screening answers. Cosmos bindings can replace the filesystem write in deployment.
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

import azure.functions as func

from api.main import app as fastapi_app
from api.ingest import fetch_active_va_alerts, payload_hash
from api.providers.azure_sms import handle_event_grid_events


app = func.FunctionApp()


@app.route(route="{*route}", auth_level=func.AuthLevel.ANONYMOUS)
def http_app(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    """Expose the complete FastAPI experience through consumption-based Azure Functions."""

    return func.AsgiMiddleware(fastapi_app).handle(req, context)


@app.timer_trigger(schedule="0 */5 * * * *", arg_name="timer", run_on_startup=False)
def ingest_nws(timer: func.TimerRequest) -> None:
    payload = fetch_active_va_alerts()
    cache = Path(tempfile.gettempdir()) / "last-mile-ingest-snapshot.json"
    safe_snapshot = {
        "fetched_at": payload["fetched_at"],
        "transport": payload["transport"],
        "count": len(payload["features"]),
        "features": [
            {"sha256": payload_hash(feature), "feature": feature}
            for feature in payload["features"]
        ],
    }
    cache.write_text(json.dumps(safe_snapshot), encoding="utf-8")
    logging.info("NWS ingest completed with %d Virginia alert(s)", safe_snapshot["count"])


@app.event_grid_trigger(arg_name="event")
def sms_event(event: func.EventGridEvent) -> None:
    """Process ACS inbound SMS and delivery reports without logging phone numbers or message bodies."""

    payload = {
        "id": event.id,
        "eventType": event.event_type,
        "data": event.get_json(),
    }
    result = handle_event_grid_events([payload])
    event_names = [item.get("event") for item in result.get("events", [])]
    logging.info("Processed Communication Services event types: %s", event_names)
