# Live Azure operational evidence

Measured against `https://lmva3fcshw5lauukqapi.azurewebsites.net` on 2026-09-24. These are bounded engineering checks, not a production availability certification.

## Performance and cold start

- Read-path concurrency probe: 40/40 HTTP 200 at concurrency 8.
- Throughput: 8.31 requests/second.
- Latency: p50 196.3 ms; p95 2,347.4 ms; maximum 3,889.5 ms.
- Observed first `/healthz` request after an explicit Function App restart: 3,722 ms, HTTP 200.
### English Foundry transformation

The earlier bottleneck (one observed seven-segment run at 20,972 ms, 3 segments withheld) has been reduced, not eliminated. Measured over six consecutive cold runs of the same seven-segment alert on 2026-09-24:

| | Before | Now |
|---|---:|---:|
| Cold wall time, mean | ~21.0 s | **9.1 s** (range 4.7–12.1 s) |
| Repeat run, same alert | ~21.0 s | **0.25 s** (cache) |
| Segments verified | 4/7 | **35/42 = 83.3%** |
| Segments served by a local fallback | 3/7 | **0** |

Four changes, in order of effect:

1. **Two-shot prompting.** Asked for a schema, the Phi-4-mini deployment invented its own JSON key names and stripped the brackets off the `[[E1]]` sentinels, which failed the entity check and forced a local fallback on 3 of 7 segments. Two worked examples fixed the shape and the brackets: 7/7 clean on the probe run.
2. **Connection reuse and parallelism.** One keep-alive client for the process instead of a fresh TLS handshake per call, and every segment of a typical alert now runs at once (`TRANSFORM_MAX_WORKERS` default 4 → 8), so wall time is set by the slowest segment rather than by the queue.
3. **Bounded retry.** 429 and 5xx are retried up to three times honouring `Retry-After`, instead of dropping straight to the local fallback.
4. **A real English meaning check.** Without embeddings, English semantic fidelity was lexical overlap, which penalised the simplification it was asked to produce. It is now Foundry reverse entailment — does the plain-language output still carry every claim the source made. This costs one extra call per segment, which is most of the remaining latency, and it is the reason withholding fell rather than a threshold being loosened.

A repeat run is served from an in-process cache of the deployment's temperature-0 responses. It is a real Foundry result without a fresh round trip, and the manifest records `cached_segments` so a fast run cannot be mistaken for a faster provider. The cache is in-process only and is empty after any restart.

Measured against the deployed Function App the same day, using a different target reading grade each time so nothing could be cache-served:

| Run | Cold | Repeat |
|---|---:|---:|
| grade 7 | 5.09 s | 0.85 s |
| grade 8 | 4.68 s | 0.90 s |
| grade 9 | 8.29 s | 3.95 s |

Live is faster than local because the Function App and the Foundry resource are in the same region.

**Throttling is real under sustained load.** The third live run, issued back to back with the first two, exhausted its three retries on one segment and landed on the local fallback (`HTTPStatusError`). Eight segments in flight against a 20,000 TPM deployment will throttle if runs are stacked; a single resident clicking once will not. The behaviour when it happens is the designed one — a named fallback recorded in the segment's provenance, never a silent failure or a dropped sentence.

**Still true:** 16.7% of English segments are withheld. The dominant cause is the model appending advice the source did not contain ("stay safe", "stay alert"), which the grounding judge correctly refuses. That is the system working, not a defect, but it does mean roughly one sentence in six is shown verbatim rather than simplified. An added third example discouraging closing advice was measured and dropped: it did not improve the rate and it cost latency.

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
- Automated tests: 185 passed, 1 intentionally skipped.
- Simulated Translator and Foundry timeouts prove deterministic fallback and expose `fallback_reason=TimeoutError`; see `docs/provider-outage-runbook.md`.
- GitHub Actions now runs the security audit on every push/PR and probes `/healthz` and `/api/status` hourly.

## Still unproven

This evidence does not establish sustained availability, agency-scale capacity, a regional disaster-recovery objective, native-speaker quality, SMS/voice delivery, or contact-center economic impact. Those require external access or human/partner data.

## Prompt-coverage acceptance check

After deployment of commit `cc2b066`, a live citizen-journey check confirmed:

- the web recovery-code and language-access controls are present;
- Azure Table continuity is active and the obsolete Cosmos capability claim is absent;
- an `RBX` packet can be created and resumed;
- an unsafe-shelter/fraud selection is classified as a sensitive human handoff;
- the copyable handoff excludes exact device coordinates and the sensitive reason;
- the stored continuity packet excludes the sensitive reason while retaining only a generic private-review flag;
- the security workflow completed successfully and `/healthz` remained healthy.
