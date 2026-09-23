# Evaluation

Run:

```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m eval.report
```

The checked-in report is deliberately narrow. It measures the deterministic fallback against the synthetic NWS-schema fixture.

## Current local results

Read the current values from `data/evaluation_report.json`; do not copy numbers from this document after changing code. At the latest run:

- 14 automated tests passed.
- Entity preservation tests cover place, road, time, measurement, phone, and URL locking plus drop/duplicate detection.
- Corruption detection covers entity deletion, duplication, sentinel alteration, dropped negation, hallucinated instruction, and dropped instruction.
- Translation quality is **not claimed** because no independent reference set is checked in.
- The ACS impact headline is **not claimed** because a dated NWS archive × ACS B16004 run has not been supplied.

## Interpreting the corruption score

Only applicable mutations count. For example, a “drop entity” case is omitted when a sentence has no locked entity; an unchanged string is not counted as a detected failure. This avoids inflating the denominator with no-op corruptions.

The current fixture is small. A competition result should add at least:

1. A held-out historical Virginia alert set spanning flood, hurricane, wildfire, winter storm, and evacuation language.
2. Independent Spanish/Vietnamese/Korean/Dari reference review or clearly labeled back-translation proxy results.
3. Foundry evaluation runs for groundedness, instruction coverage, and explanation quality.
4. Azure p50/p95 measurements with warm and cold paths separated.
5. False-abstention results by language and event type.

## ACS impact method

Use a fixed 12-month window and preserve the raw inputs:

1. Download the NWS Virginia alert archive for the window and de-duplicate updates by CAP ID/reference chain.
2. Intersect alert polygons with Census geography. Document how alerts without polygons are handled.
3. Download ACS table B16004 for the same geography/vintage.
4. Sum “speaks English less than very well” cells only once per relevant population exposure definition.
5. Sanity-check against county and state population totals.
6. Publish numerator, denominator, date window, geography method, and limitations with the headline.

`eval/impact.py` exits instead of inventing a number when the required source files are absent.

