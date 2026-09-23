from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .metrics import evaluate_clean_and_latency, evaluate_corruption_detection
from .bundle_size import measure as measure_bundle


ROOT = Path(__file__).resolve().parents[1]


def build_report() -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Deterministic local fallback against the checked-in NWS-schema demo fixture.",
        "warning": "These are harness results, not claims about a production deployment or Azure model quality.",
        "clean": evaluate_clean_and_latency(),
        "corruption_detection": evaluate_corruption_detection(),
        "translation_quality": {
            "status": "not_claimed",
            "reason": "No independent reference translations are checked in. Provider confidence is not reported as translation quality.",
        },
        "impact_estimate": {
            "status": "not_claimed",
            "reason": "Requires a dated 12-month NWS archive and ACS B16004 run; do not invent a headline number.",
        },
        "connectivity": measure_bundle(),
    }


if __name__ == "__main__":
    report = build_report()
    path = ROOT / "data" / "evaluation_report.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
