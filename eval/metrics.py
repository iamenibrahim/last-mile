from __future__ import annotations

import statistics
import time

from api.entities import lock_entities, restore_entities
from api.ingest import load_cached_alert
from api.transform import transform_alert
from api.verify import verify_segment
from eval.corrupt import corruptions


def evaluate_corruption_detection() -> dict:
    instruction = load_cached_alert()["properties"]["instruction"]
    cases = []
    for segment in [value.strip() for value in instruction.split(".") if value.strip()]:
        source = segment + "."
        locked = lock_entities(source, ["Norfolk", "Chesapeake", "Virginia Beach"])
        for kind, corrupted in corruptions(locked.masked).items():
            if corrupted == locked.masked:
                continue
            restored = restore_entities(corrupted, locked.entities)
            result = verify_segment(
                source,
                corrupted,
                restored,
                locked.entities,
                provider_confidence=0.96,
                target_language="en",
                provider="deterministic-local",
                is_instruction=True,
            )
            cases.append({"class": kind, "caught": not result["passed"]})
    by_class = {}
    for kind in sorted({item["class"] for item in cases}):
        values = [item["caught"] for item in cases if item["class"] == kind]
        by_class[kind] = {
            "caught": sum(values),
            "total": len(values),
            "recall": round(sum(values) / len(values), 3),
        }
    return {
        "overall_recall": round(sum(item["caught"] for item in cases) / len(cases), 3),
        "by_class": by_class,
        "cases": len(cases),
    }


def evaluate_clean_and_latency(iterations: int = 20) -> dict:
    alert = load_cached_alert()
    latencies = []
    false_abstentions = 0
    result = None
    for _ in range(iterations):
        start = time.perf_counter()
        result = transform_alert(alert, language="en")
        latencies.append((time.perf_counter() - start) * 1000)
        false_abstentions += sum(item["status"] == "verbatim_abstained" for item in result["segments"])
    assert result is not None
    p95_index = max(0, int(len(latencies) * 0.95) - 1)
    sorted_latencies = sorted(latencies)
    clean_segments = iterations * len(result["segments"])
    return {
        "iterations": iterations,
        "segments": clean_segments,
        "false_abstention_rate": round(false_abstentions / max(1, clean_segments), 3),
        "latency_ms": {
            "p50": round(statistics.median(latencies), 2),
            "p95": round(sorted_latencies[p95_index], 2),
        },
        "reading_grade": {"source": result["source_grade"], "output": result["output_grade"]},
    }
