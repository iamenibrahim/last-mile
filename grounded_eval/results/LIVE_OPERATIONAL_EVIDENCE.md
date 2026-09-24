# Live Azure operational evidence

Measured against `https://lmva3fcshw5lauukqapi.azurewebsites.net` on 2026-09-24. These are bounded engineering checks, not a production availability certification.

## Performance and cold start

- Read-path concurrency probe: 40/40 HTTP 200 at concurrency 8.
- Throughput: 8.31 requests/second.
- Latency: p50 196.3 ms; p95 2,347.4 ms; maximum 3,889.5 ms.
- Observed first `/healthz` request after an explicit Function App restart: 3,722 ms, HTTP 200.
- English Foundry alert transformation remains a known bottleneck: one observed seven-segment run took 20,972 ms and withheld 3 segments. This result must not be represented as resolved.

## Multilingual verification

The new round-trip verifier reduced false withholding while retaining number, entity, negation, instruction, and grounding guards. See `LIVE_MULTILINGUAL_AZURE.md` for the full scope and caveats.

| Language | Previous withholding | Current withholding | Current latency |
|---|---:|---:|---:|
| Spanish | 57.1% | 14.3% | 2,003.5 ms |
| Arabic | 71.4% | 0.0% | 1,581.2 ms |
| Dari | 57.1% | 14.3% | 1,705.3 ms |
| Tagalog | 85.7% | 28.6% | 1,729.9 ms |

All four runs had zero locked-entity failures and zero provider errors. This is not a substitute for native-speaker review.

## Continuity and restart recovery

Packet `RBX-YALBS` was created and successfully retrieved before and after an explicit Azure Function App restart. The continuity record was served from Azure Table Storage rather than temporary Function disk. The packet excludes name, street address, SSN, bank data, phone number, and uploaded documents and expires after 24 hours.

## Telemetry

Application Insights received the new PII-free `http_request_completed` traces. A 30-minute query observed 53 completed requests, zero non-2xx results, p50 application duration 8.6 ms, p95 1,210.6 ms, and maximum 20,266.9 ms. Each HTTP response also carries a generated `X-Request-ID`; no request body is logged by this middleware.

## Security and provider failure

- Production dependency audit: no known vulnerabilities found.
- Bandit scan: no medium/high-severity finding at medium-or-higher confidence.
- Automated tests: 179 passed, 1 intentionally skipped.
- Simulated Translator and Foundry timeouts prove deterministic fallback and expose `fallback_reason=TimeoutError`; see `docs/provider-outage-runbook.md`.
- GitHub Actions now runs the security audit on every push/PR and probes `/healthz` and `/api/status` hourly.

## Still unproven

This evidence does not establish sustained availability, agency-scale capacity, a regional disaster-recovery objective, native-speaker quality, SMS/voice delivery, or contact-center economic impact. Those require external access or human/partner data.
