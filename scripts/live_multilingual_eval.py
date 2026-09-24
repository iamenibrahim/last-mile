"""Low-cost live Azure evaluation for the four challenge languages.

This intentionally makes one alert transformation per language. It is a smoke
evaluation of the deployed providers, not a statistically representative
language-quality study. Results contain aggregate metadata only—no secrets or
citizen data.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import time
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "grounded_eval" / "results"
LANGUAGES = ("es", "ar", "prs", "tl")


def evaluate(base_url: str, language: str) -> dict:
    started = time.perf_counter()
    response = httpx.post(
        f"{base_url}/api/transform",
        json={"language": language, "grade": 6, "simulate_failure": False},
        timeout=240.0,
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    response.raise_for_status()
    payload = response.json()
    segments = payload.get("segments", [])
    statuses = collections.Counter(segment.get("status", "unknown") for segment in segments)
    reasons = collections.Counter(
        segment.get("reason") for segment in segments if segment.get("reason")
    )
    provider_errors = collections.Counter(
        str(segment.get("provider", {}).get("fallback_reason"))
        for segment in segments
        if segment.get("provider", {}).get("fallback_reason")
    )
    provider_engines = sorted(
        {segment.get("provider", {}).get("engine", "unknown") for segment in segments}
    )
    safety_modes = sorted(
        {segment.get("output_safety", {}).get("mode", "unknown") for segment in segments}
    )
    locked_entities = sum(len(segment.get("entities", [])) for segment in segments)
    locked_entity_failures = 0
    for segment in segments:
        entity_check = segment.get("verification", {}).get("checks", {}).get("entity_integrity")
        if entity_check and not entity_check.get("passed", False):
            locked_entity_failures += 1
    successful = statuses["translated_verified"]
    withheld = statuses["verbatim_abstained"]
    return {
        "language": language,
        "http_status": response.status_code,
        "segments": len(segments),
        "successful_transformations": successful,
        "withheld_transformations": withheld,
        "withholding_rate": round(withheld / max(1, len(segments)), 4),
        "locked_entities": locked_entities,
        "locked_entity_failures": locked_entity_failures,
        "provider_errors": dict(provider_errors),
        "provider_engines": provider_engines,
        "content_safety_modes": safety_modes,
        "withholding_reasons": dict(reasons),
        "latency_ms": elapsed_ms,
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# Live Azure multilingual evaluation",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "> One deployed alert per language. This is a provider smoke evaluation, not a native-speaker quality study.",
        "",
        "| language | successful | withheld | withholding | locked entities | entity failures | provider errors | latency |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["languages"]:
        lines.append(
            "| {language} | {successful_transformations}/{segments} | {withheld_transformations} | "
            "{withholding_rate:.1%} | {locked_entities} | {locked_entity_failures} | {errors} | {latency_ms:.1f} ms |".format(
                **row, errors=sum(row["provider_errors"].values())
            )
        )
    lines += [
        "",
        "Provider errors count explicit cloud fallbacks reported by the response. Withholding is expected fail-closed behavior when a transformed segment cannot be verified.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        default="https://lmva3fcshw5lauukqapi.azurewebsites.net",
    )
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    report = {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "base_url": base_url,
        "scope": "one deployed cached NWS alert per language",
        "languages": [evaluate(base_url, language) for language in LANGUAGES],
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    json_path = RESULTS / "live_multilingual_azure.json"
    markdown_path = RESULTS / "LIVE_MULTILINGUAL_AZURE.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
