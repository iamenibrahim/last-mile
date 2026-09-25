"""One bounded readiness command; no calls, SMS, or generative provider work.

Run with the project's Python: scripts/readiness_report.py [--live].
Subprocess diagnostics and HTTP bodies are deliberately not copied to the report.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://lmva3fcshw5lauukqapi.azurewebsites.net"
EXPECTED_SKIP = "this alert has no segment eligible for swap_road"
PROFILE = {"location": "24370", "jurisdiction": "Smyth County", "needs": ["housing"],
           "circumstances": ["displaced"], "context_reviewed": True, "surge_mode": True}


def command(args: list[str], *, local: bool = False) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    if local:
        # Prevent a developer's cloud configuration from making tests send traffic.
        for key in list(env):
            if key.startswith(("AZURE_", "FOUNDRY_", "SMS_", "CALL_", "APPLICATIONINSIGHTS_")):
                env.pop(key)
        env.update(APP_ENV="local", SURGE_MODE="false")
    executable = shutil.which(args[0])
    if not executable:
        raise FileNotFoundError("Required executable unavailable")
    return subprocess.run([executable, *args[1:]], cwd=ROOT, env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=300, check=False)


def parse_pytest(path: Path) -> dict:
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    skipped = [case for case in cases if case.find("skipped") is not None]
    failed = sum(case.find("failure") is not None or case.find("error") is not None for case in cases)
    expected = [case for case in skipped if case.get("name") == "test_each_corruption_class_is_caught[swap_road]"
                and EXPECTED_SKIP in case.find("skipped").get("message", "")]
    return {"total": len(cases), "passed": len(cases) - len(skipped) - failed,
            "failed": failed, "skipped": len(skipped), "expected_skips": len(expected),
            "unexpected_skips": len(skipped) - len(expected),
            "expected_skip_reason": EXPECTED_SKIP}


def exit_status(report: dict) -> int:
    return int(any(check["status"] == "failed" or (check["required"] and check["status"] != "passed")
                   for check in report["checks"]))


def collect(*, live: bool = False, base_url: str = BASE_URL) -> dict:
    report: dict[str, Any] = {
        "schema_version": 1, "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "checks": [], "human_evidence": {"verified": False,
            "limitations": ["handset audibility", "native-speaker review", "accessibility certification",
                            "agency approval", "contact-center impact"]},
        "scope": "Bounded readiness evidence; no calls, SMS, or paid generative transformations",
    }

    def check(name, scope, action, required=True):
        item = {"name": name, "scope": scope, "required": required}
        try:
            passed, evidence = action()
            item.update(status="passed" if passed else "failed", evidence=evidence)
        except Exception as error:
            # Exception strings may contain URLs, response bodies, credentials or codes.
            item.update(status="failed" if required else "unavailable", error_type=type(error).__name__)
        report["checks"].append(item)

    def source():
        head = command(["git", "rev-parse", "HEAD"])
        dirty = command(["git", "status", "--porcelain"])
        commit = head.stdout.strip()
        return head.returncode == dirty.returncode == 0 and bool(re.fullmatch(r"[0-9a-f]{40}", commit)), {
            "commit": commit if re.fullmatch(r"[0-9a-f]{40}", commit) else None,
            "dirty": bool(dirty.stdout.strip()), "changed_path_count": len(dirty.stdout.splitlines()),
            "tested_tree": "working tree including uncommitted changes"}

    check("source", "local", source)

    def source_records():
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from api.reliability import assess_freshness, detect_source_conflicts

        records = json.loads((ROOT / "data/programs.json").read_text(encoding="utf-8"))
        stale = sum(assess_freshness(row)["stale"] for row in records)
        conflicts = detect_source_conflicts(records)
        return bool(records) and not conflicts["conflict_detected"], {
            "total": len(records), "stale": stale, "current": len(records) - stale,
            "conflicts": len(conflicts["conflicts"])}

    check("source_records", "local", source_records)
    with tempfile.TemporaryDirectory(prefix="last-mile-readiness-") as temporary:
        junit = Path(temporary) / "pytest.xml"

        def tests():
            result = command([sys.executable, "-m", "pytest", "-q", "-rs", "-p", "no:cacheprovider",
                              f"--junitxml={junit}"], local=True)
            totals = parse_pytest(junit)
            return result.returncode == 0 and totals["passed"] > 0 and totals["unexpected_skips"] == 0, totals

        check("python_tests", "local", tests)
        for name, args in [
            ("javascript_syntax", ["node", "--check", "web/app.js"]),
            ("python_syntax", [sys.executable, "-m", "compileall", "-q", "api", "grounded", "scripts"]),
            ("diff_whitespace", ["git", "diff", "--check"]),
        ]:
            check(name, "local", lambda args=args: (command(args, local=True).returncode == 0, {}))

        def replay():
            result = command([sys.executable, "scripts/replay_scenarios.py"], local=True)
            body = json.loads(result.stdout)
            totals = {key: body[key] for key in ("scenario_count", "passed", "failed")}
            return result.returncode == 0 and totals["failed"] == 0 and totals["passed"] > 0, totals

        check("scenario_replay", "simulated_local", replay)
        if live:
            # Reject embedded credentials/query strings and use the reviewed deployment only.
            if base_url.rstrip("/") != BASE_URL:
                raise ValueError("Live target must be the reviewed deployment URL")
            with httpx.Client(base_url=BASE_URL, timeout=60, follow_redirects=False) as client:
                packet: dict = {}

                def request(method, path, body=None):
                    response = client.request(method, path, json=body) if body is not None else client.request(method, path)
                    response.raise_for_status()
                    if not response.headers.get("x-request-id") or response.headers.get("x-last-mile-mode") not in {"normal", "surge"}:
                        raise AssertionError("Operational headers missing")
                    return response.json()

                check("health", "deployed", lambda: (request("GET", "/healthz") == {"ok": True}, {}))

                def status():
                    body = request("GET", "/api/status")
                    providers = body.get("providers", {})
                    evidence = {key: providers.get(key) for key in (
                        "azure_table_continuity", "azure_key_vault_signing",
                        "azure_communication_services_sms", "azure_communication_services_voice")}
                    return body.get("status") == "ready" and all(evidence[key] is True for key in (
                        "azure_table_continuity", "azure_key_vault_signing")), evidence

                check("status", "deployed", status)

                def freshness():
                    body = request("GET", "/api/programs/freshness")
                    records = body["records"]
                    return bool(records) and all("reasons" in row for row in records), {
                        "total": len(records), "stale": body["stale_count"],
                        "current": len(records) - body["stale_count"],
                        "note": "Stale historical records are disclosed, not asserted current"}

                check("program_freshness", "deployed", freshness)

                def conflicts():
                    body = request("GET", "/api/source-conflicts")
                    return not body["conflict_detected"], {"conflicts": len(body["conflicts"])}

                check("source_conflicts", "deployed", conflicts)

                def navigation():
                    body = request("POST", "/api/navigate", PROFILE)
                    recommendations = body.get("recommendations", [])
                    return bool(recommendations) and all(row.get("evidence", {}).get("rule") and
                        row.get("explanation_provider", "").startswith("rules + reviewed") for row in recommendations), {
                        "recommendations": len(recommendations), "deterministic": True}

                check("navigation_evidence", "deployed", navigation)

                def chaos():
                    modes = ["foundry_down", "translator_down", "maps_down", "stale_source", "bad_translation", "no_network"]
                    body = request("POST", "/api/chaos/evaluate", {"modes": modes})
                    outcomes = body.get("outcomes", [])
                    return body.get("simulated") is True and len(outcomes) == 6 and all(row.get("safe") for row in outcomes), {"modes": len(outcomes)}

                check("chaos_fallbacks", "simulated_deployed", chaos)

                def create():
                    body = request("POST", "/api/packet", PROFILE)
                    packet.update(body.get("packet", {}))
                    return body.get("status") == "complete" and bool(packet.get("continuity", {}).get("code")), {
                        "anonymous": True, "expires_in_hours": packet.get("continuity", {}).get("expires_in_hours"),
                        "algorithm": packet.get("proof", {}).get("algorithm")}

                check("packet_generation", "deployed", create)
                check("packet_signature", "deployed", lambda: (
                    request("POST", "/api/packet/verify", {"packet": packet}).get("valid") is True, {}))

                def saved(path, key):
                    body = request("GET", path + packet["continuity"]["code"])
                    return body.get(key) is True, {}

                check("packet_resume", "deployed", lambda: saved("/api/continue/", "resumed"))
                check("packet_handoff", "deployed", lambda: saved("/api/handoff/", "packet_verified"))

                def diff():
                    body = request("GET", "/api/packet/diff/" + packet["continuity"]["code"])
                    return body.get("changed") is False and body.get("changes") == [], {"changed": body.get("changed")}

                check("packet_source_diff", "deployed", diff)

                def snapshot():
                    body = request("GET", "/api/packet/offline/" + packet["continuity"]["code"])
                    server = request("POST", "/api/offline/verify", {"snapshot": body})
                    signing_key = request("GET", "/api/signing-key")
                    path = Path(temporary) / "snapshot.json"
                    trusted_key_path = Path(temporary) / "trusted-public-jwk.json"
                    path.write_text(json.dumps(body), encoding="utf-8")
                    trusted_key_path.write_text(json.dumps(signing_key.get("public_jwk")), encoding="utf-8")
                    result = command([sys.executable, "scripts/verify_offline_snapshot.py", str(path),
                                      "--trusted-jwk", str(trusted_key_path)], local=True)
                    verified = json.loads(result.stdout)
                    return (server.get("valid") is True and result.returncode == 0
                            and verified.get("valid") is True
                            and verified.get("trust_anchor") == "trusted_jwk_file"), {
                        "server_verified": server.get("valid"),
                        "public_key_local_verified": verified.get("valid"),
                        "trust_anchor": verified.get("trust_anchor")}

                check("signed_snapshot", "deployed_and_local", snapshot)

                def transform():
                    body = request("POST", "/api/transform", {"language": "es", "surge_mode": True})
                    segments = body.get("segments", [])
                    safe = all(row.get("verification", {}).get("passed") or row.get("status") == "verbatim_abstained" for row in segments)
                    return bool(segments) and safe and body.get("provider_mode") == "surge-deterministic", {
                        "segments": len(segments), "safe": safe, "deterministic": body.get("provider_mode") == "surge-deterministic"}

                check("surge_transformation", "deployed", transform)

                def ui():
                    html = client.get("/")
                    script = client.get("/assets/app.js")
                    html.raise_for_status()
                    script.raise_for_status()
                    tokens = [token in html.text for token in ('id="run-chaos"', 'id="preference-profile"', 'id="download-snapshot"')]
                    tokens += [token in script.text for token in ("evidence-trace", "source_freshness")]
                    return all(tokens), {"present": sum(tokens), "expected": len(tokens), "commit_attestation": False}

                check("ui_tokens", "deployed", ui)

            def workflow():
                result = command(["gh", "run", "list", "--workflow", "deploy-function-app.yml", "--branch", "main",
                                  "--limit", "1", "--json", "headSha,status,conclusion,url"])
                row = json.loads(result.stdout)[0]
                return result.returncode == 0 and row["conclusion"] == "success", {
                    "reported_commit": row["headSha"], "status": row["status"], "conclusion": row["conclusion"],
                    "url": row["url"], "limitation": "Workflow-reported commit; runtime does not expose commit attestation"}

            check("deployment_workflow", "deployment_metadata", workflow)

            def telemetry():
                since = report["generated_at"]
                result = command(["az", "monitor", "app-insights", "query", "--app", "lmva3fcshw5lauukqinsights",
                                  "--resource-group", "last-mile-student-rg", "--analytics-query",
                                  f"traces | where timestamp >= datetime({since}) | where message contains 'http_request_failed' | summarize failures=count()",
                                  "--output", "json", "--only-show-errors"])
                if result.returncode:
                    raise RuntimeError("Telemetry unavailable")
                count = int(json.loads(result.stdout)["tables"][0]["rows"][0][0])
                return count == 0, {"failures": count, "since": since,
                                    "limitation": "Ingestion may lag; query absence is not proof of no failures"}

            check("application_insights", "deployed_telemetry", telemetry, required=False)
    report["result"] = "passed" if exit_status(report) == 0 else "failed"
    report["required_failures"] = sum(row["required"] and row["status"] != "passed" for row in report["checks"])
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Also probe the reviewed Azure deployment")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = collect(live=args.live)
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered)
    return exit_status(report)


if __name__ == "__main__":
    raise SystemExit(main())
