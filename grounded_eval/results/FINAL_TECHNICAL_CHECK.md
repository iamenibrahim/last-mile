# Final technical check — September 25, 2026 (ET)

Base: `iamenibrahim/last-mile`, `e12364a8a8891dc2af79499cc13faf7961d72a75`.
Fixes are on `codex/final-technical-checks`; these results do not imply that
the fixes have been merged or deployed. JSON timestamps use UTC (September 26).

## Verified

- Local Python 3.12 suite: **297 passed, 1 expected skip**. The fixture has no
  road eligible for the skipped `swap_road` corruption test.
- All five browser JavaScript files parse. Four deterministic scenario replays pass.
- Production dependency audit: no known vulnerabilities in the resolved requirements.
- Bandit: no findings at the CI medium/high severity and medium/high confidence gate.
- Live application checks: health and provider status, ten source records with no
  reported conflicts, deterministic navigation, six simulated outage modes, RS256
  packet generation/verification, recovery-code resume, handoff, source diff, signed
  offline snapshot verified against the separately fetched public key, and surge
  transformation all passed.
- The deployed base commit's [deployment](https://github.com/iamenibrahim/last-mile/actions/runs/36204455943)
  and [security audit](https://github.com/iamenibrahim/last-mile/actions/runs/36204455940)
  both succeeded, verified through the authenticated GitHub API.
- Local browser: low-data toggle, ambiguous ZIP selection, Smyth County results,
  citations and provenance render. The original page verifies; deliberate tampering
  fails both exact-citation and render-digest checks. Local providers are explicitly labeled.

Evidence: `final_local_readiness.json`, `final_readiness.json`,
`final_dependency_audit.json`, and `final_bandit.json` in this directory.
The live readiness script reports one required failure because `gh` is absent;
the deployment metadata was independently verified through GitHub's API above.
Application Insights was unavailable because `az` is absent. Neither absence is
reported as a successful telemetry check. The runtime has no commit attestation.

## Fixes

- Register the main PWA worker at the root so it can control the main page.
  Automatically cache only successful public-shell requests. Recovery API, audio,
  query-string and third-party responses are excluded. Purge the old app cache
  on upgrade while preserving unrelated caches. Explicit opt-in plan saving stays.
- Bound cloud sentence simplification and verification to four workers across
  requests, retaining result order and all integrity/abstention checks. Local
  language providers remain serial. The redesigned live navigator stalled after
  county selection; this removes its serial cloud-call bottleneck. **Improved
  live latency is not yet measured.**
- Bound navigator fetches to 90 seconds with a visible retry/help message and
  prevent an older response from replacing a newer request's results.
- Remove two unsafe local substitutions: `following` to `these` and
  `information` to `news`. Regression checks preserve deadline and bank-data wording.
- Add PR/main technical CI and require tests, syntax, scenarios, dependency audit,
  and the configured Bandit gate before the deployment action runs.
- Reconcile stale voice, continuity, repository and test-count documentation.

## Before recording

1. Merge/deploy the fixes after review; rerun the grounded county-selection flow
   against Azure and measure its completion time. A local pass is not cloud evidence.
2. Test the current voice keys `1`, `2`, `#`, `9`, `0` on a verified handset.
   This pass did not place a call or send SMS.
3. Run the planned keyboard/screen-reader and native-speaker walkthroughs.

SMS sending and Copilot Studio publication remain externally blocked as documented.
This is a bounded technical pass, not production certification or a measured
contact-center impact claim. Demo/deck/recording work remains separate.
