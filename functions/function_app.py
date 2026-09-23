"""Azure Functions timer trigger for NWS ingest.

The function stores only alert material. It does not receive or persist citizen
screening answers. Cosmos bindings can replace the filesystem write in deployment.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import azure.functions as func

from api.ingest import fetch_active_va_alerts, payload_hash


app = func.FunctionApp()


@app.timer_trigger(schedule="0 */5 * * * *", arg_name="timer", run_on_startup=False)
def ingest_nws(timer: func.TimerRequest) -> None:
    payload = fetch_active_va_alerts()
    cache = Path(__file__).resolve().parents[1] / "data" / "ingest_snapshot.json"
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

