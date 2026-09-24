"""Cost-bounded concurrency and latency probe for the deployed read paths."""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import math
import statistics
import time
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "grounded_eval" / "results"
PATHS = ("/healthz", "/api/status", "/grounded/api/corpus/stats")


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1))
    return round(ordered[index], 1)


async def probe(base_url: str, requests: int, concurrency: int) -> dict:
    semaphore = asyncio.Semaphore(concurrency)
    results: list[dict] = []
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        await client.get(f"{base_url}/healthz")

        async def one(index: int) -> None:
            path = PATHS[index % len(PATHS)]
            async with semaphore:
                started = time.perf_counter()
                try:
                    response = await client.get(f"{base_url}{path}")
                    results.append(
                        {
                            "path": path,
                            "status": response.status_code,
                            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                        }
                    )
                except Exception as error:
                    results.append(
                        {
                            "path": path,
                            "status": 0,
                            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                            "error": type(error).__name__,
                        }
                    )

        wall_started = time.perf_counter()
        await asyncio.gather(*(one(index) for index in range(requests)))
        wall_ms = round((time.perf_counter() - wall_started) * 1000, 1)

    latencies = [row["latency_ms"] for row in results]
    successes = sum(1 for row in results if row["status"] == 200)
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "base_url": base_url,
        "scope": "read-only health, provider-status, and corpus-stat endpoints",
        "requests": requests,
        "concurrency": concurrency,
        "successes": successes,
        "failures": requests - successes,
        "success_rate": round(successes / max(1, requests), 4),
        "wall_ms": wall_ms,
        "requests_per_second": round(requests / max(0.001, wall_ms / 1000), 2),
        "latency_ms": {
            "p50": round(statistics.median(latencies), 1),
            "p95": percentile(latencies, 0.95),
            "max": round(max(latencies), 1),
        },
        "errors": [row for row in results if row.get("error") or row["status"] != 200],
    }


def markdown(report: dict) -> str:
    latency = report["latency_ms"]
    return (
        "# Live Azure performance probe\n\n"
        f"Generated: {report['generated_at']}\n\n"
        f"- Scope: {report['scope']}\n"
        f"- Requests: **{report['requests']}** at concurrency **{report['concurrency']}**\n"
        f"- Success: **{report['successes']}/{report['requests']} ({report['success_rate']:.1%})**\n"
        f"- Throughput: **{report['requests_per_second']} requests/second**\n"
        f"- Latency: **p50 {latency['p50']} ms, p95 {latency['p95']} ms, max {latency['max']} ms**\n"
        f"- Failures: **{report['failures']}**\n\n"
        "This is a small, cost-bounded engineering probe, not a production capacity certification.\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://lmva3fcshw5lauukqapi.azurewebsites.net")
    parser.add_argument("--requests", type=int, default=40)
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()
    report = asyncio.run(probe(args.base_url.rstrip("/"), args.requests, args.concurrency))
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "live_performance.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    rendered = markdown(report)
    (RESULTS / "LIVE_PERFORMANCE.md").write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0 if report["failures"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
