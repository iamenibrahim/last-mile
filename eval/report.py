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
        "scope": (
            "clean and corruption_detection: deterministic local fallback against the single synthetic "
            "demo fixture. real_alert_corpus: the grounded pipeline over 80 real NWS alerts; quote that one."
        ),
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
        "real_alert_corpus": real_alert_corpus(),
    }


def real_alert_corpus() -> dict:
    """The headline numbers: the grounded pipeline over 80 real NWS alerts.

    Copied from grounded_eval/results/metrics_en.json, which
    `python -m grounded_eval.metrics --lang en --ablate` writes. Nothing is recomputed here.
    """
    path = ROOT / "grounded_eval" / "results" / "metrics_en.json"
    if not path.exists():
        return {"status": "not_run", "notice": "Run python -m grounded_eval.metrics --lang en --ablate."}
    metrics = json.loads(path.read_text(encoding="utf-8"))
    abstention = {key: value for key, value in metrics["abstention"].items() if key != "sweep"}
    return {
        "scope": f"{metrics['corpus_size']} real NWS alerts in data/grounded/cached_alerts, language {metrics['lang']}.",
        "engines": metrics["engines"],
        "engine_warning": (
            "Local stub engines measure whether the pipeline catches the failures it is built to catch, "
            "not model quality. Rerun with Azure keys for the Foundry and Translator figures."
            if metrics["engines"].get("judge", "").startswith("local")
            else "Azure engines."
        ),
        "generated_at": metrics["generated_at"],
        "readability": {key: value for key, value in metrics["readability"].items() if key != "finding"},
        "entity_preservation": metrics["entity_preservation"],
        "abstention": abstention,
        "ablation_no_entity_lock": metrics["ablation_no_entity_lock"],
        "latency_ms": metrics["latency_ms"],
        "instruction_coverage_finding": metrics["instruction_coverage_finding"],
    }


if __name__ == "__main__":
    report = build_report()
    path = ROOT / "data" / "evaluation_report.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
