# Overnight Execution Plan — Last-Mile Disaster Navigator

**Execution window:** Friday, September 25, 2026, approximately 12:35 AM–8:30 AM ET

**Repository:** `iamenibrahim/rubicon`

**Branch:** `main`

**Live application:** <https://lmva3fcshw5lauukqapi.azurewebsites.net>

**Starting production commit:** `e62eda8`

**Starting local result:** 216 passed, 1 intentionally skipped

**Starting production result:** deployment successful; 15/15 broad smoke checks and 10/10 reliability checks passed
**Owner of this runbook:** Codex, operating autonomously within the limits below

---

## 1. Mission

Use the overnight window to make the project more reliable, auditable,
demonstrable, and submission-ready without requiring a person to answer a call,
approve a purchase, grant tenant access, supply credentials, interpret another
language, or make a product decision.

The priority is not raw feature count. The priority is a defensible technical
submission whose claims can be traced to tests, live endpoints, checked-in
evidence, and explicit limitations.

The overnight agent should repeatedly:

1. Select the highest-priority unchecked item that can be completed safely.
2. Inspect the current implementation and tests before changing it.
3. Make the smallest coherent change that materially improves readiness.
4. Verify locally in proportion to risk.
5. Commit only files changed for that coherent batch.
6. Deploy runtime-affecting batches through the existing GitHub Actions workflow.
7. Verify production and inspect telemetry for hidden failures.
8. Record exact evidence in this document.

Do not spend the night polishing prose while a test, safety guard, or production
failure remains unresolved.

---

## 2. Non-negotiable safety and scope boundaries

These rules override every work item below.

### 2.1 Never perform these actions autonomously

- Do not place a real phone call, send an SMS, contact 211, contact FEMA, contact
  a government employee, or message any third party.
- Do not attempt a live call transfer to 211. The current `0` branch may provide
  human-help instructions and hang up; it must not silently initiate another call.
- Do not purchase an ACS number, paid sender, license, Azure capacity, domain,
  service plan, or any other resource.
- Do not enroll in trials, accept legal terms, bypass GMU tenant controls, or
  attempt to obtain Copilot Studio access.
- Do not submit the competition entry, upload a final video, or publish a deck on
  the user's behalf.
- Do not make claims of native-speaker validation, production accessibility
  certification, agency approval, measured call-center savings, Virginia data
  residency, production scale, or live SMS delivery.
- Do not expose `.env`, `azure-settings.txt`, connection strings, publish profiles,
  phone numbers, or other secrets in logs, commits, test artifacts, or responses.
- Do not weaken abstention, entity locking, deterministic escalation, source
  conflict handling, signature verification, consent gates, or privacy controls to
  make a demo appear more successful.
- Do not delete, reset, overwrite, or broadly reformat user-authored work.
- Do not use `git reset --hard`, destructive checkout commands, force-push, or
  recursive deletion.

### 2.2 Pre-existing dirty files that must be preserved

At the start of this run, the following files or artifacts were already modified
or untracked independently of the new overnight runbook. Treat them as user work.
Do not stage, rewrite, discard, or commit them unless an overnight task requires a
specific, minimal, clearly attributable update:

- `HANDOFF.md`
- `TODO.md`
- `docs/demo-script.md`
- `docs/prompt-coverage.md`
- `grounded_eval/results/LIVE_OPERATIONAL_EVIDENCE.md`
- `infra/DEPLOYED.md`
- `deliverables/Last-Mile-Navigator-Pitch-Submission.pptx`
- `grounded_eval/results/FINAL_LIVE_SMOKE.md`
- `grounded_eval/results/final_live_smoke.json`
- `scripts/final_live_smoke.py`

Before every commit, run `git status --short` and stage exact paths only.

### 2.3 Allowed autonomous actions

- Read project files, Git history, GitHub Actions status, and Azure telemetry.
- Add or refine code, tests, fixtures, scripts, and technical documentation.
- Run local unit, contract, replay, security, syntax, and performance checks.
- Make bounded, non-sensitive live API requests.
- Create anonymous 24-hour recovery packets for testing.
- Push a scoped commit to `main` when all local gates pass.
- Wait for the existing production deployment workflow.
- Fix forward if production validation discovers a defect.
- Update this runbook with checked boxes, timestamps, commit IDs, workflow URLs,
  measurements, and exact limitations.

---

## 3. Starting baseline

### 3.1 Production state

- [x] Live Function App responds at the documented URL.
- [x] Production commit `e62eda8` deployed successfully.
- [x] Azure Table continuity reports ready.
- [x] ACS voice reports ready.
- [x] ACS SMS reports unavailable, as expected for the trial number.
- [x] Key Vault signing reports RS256 and a public verification key.
- [x] Broad production smoke: 15/15 passed after the latest deployment.
- [x] Reliability production checks: 10/10 passed.
- [x] Scenario replay: 4/4 passed.
- [x] Surge transformation returned seven safe segments using the deterministic path.
- [x] Application Insights showed no `http_request_failed` traces after the fix.

### 3.2 Implemented reliability features

- [x] Program freshness metadata and API.
- [x] Recommendation evidence traces.
- [x] Packet field-level contradiction detector.
- [x] Failure-mode dashboard and API.
- [x] Recommendation and packet provenance graphs.
- [x] JSON scenario replay.
- [x] Accessibility preference profile.
- [x] Structured, non-sensitive handoff packet.
- [x] Source conflict detector.
- [x] Saved-packet source diff.
- [x] Signed offline snapshot export and verifier.
- [x] Automatic surge-mode degradation.
- [x] Updated Virginia SNAP application destination.

### 3.3 Known honest limitations

- A second end-to-end real handset walkthrough has not occurred.
- Phone keypad branches are software-tested, not all human-audibility tested.
- Pressing `0` provides 211 instructions; it does not transfer the call.
- SMS is implemented but cannot send from the current trial configuration.
- Copilot Studio publication is blocked by tenant licensing/administration.
- The main recovery flow is a historical DR-4831-VA replay; the application
  deadline passed in 2024.
- The student deployment is in Canada Central, not Virginia or another US region.
- Multilingual results are mechanically verified but not native-speaker approved.
- No measured contact-center outcome or economic-impact result exists.

---

## 4. Standard work loop for every hourly run

Follow this sequence every time the overnight task wakes.

### Step A — Establish state

```powershell
git branch --show-current
git status --short
git log -3 --oneline --decorate
gh run list --workflow deploy-function-app.yml --limit 3
```

Confirm that `main`, `origin/main`, and the last known deployed commit agree. If
another actor changed the branch or working tree, reassess before editing.

### Step B — Select one coherent batch

- Choose the highest-priority unchecked batch below.
- Prefer completing and verifying one batch over partially touching many.
- If a batch is already satisfied by existing code, add or improve the test that
  proves it, record the evidence, and mark it complete.
- If a task requires human judgment or external authority, mark it `BLOCKED` with
  the exact dependency and move on.

### Step C — Inspect before editing

- Find relevant code with `rg` or `rg --files`.
- Read the existing tests and data contracts.
- Check whether a similar guard already exists.
- Avoid duplicating logic across `api/` and `grounded/` unless the two surfaces
  truly require separate implementations.

### Step D — Implement safely

- Use `apply_patch` for source edits.
- Preserve API compatibility unless a breaking change fixes a security defect.
- Keep deterministic rules authoritative.
- Keep optional cloud work behind fallbacks.
- Do not add new paid dependencies or infrastructure.
- Do not add sensitive fields to packet, telemetry, or handoff schemas.

### Step E — Run local gates

At minimum:

```powershell
node --check web/app.js
.\.venv\Scripts\python.exe -m compileall -q api grounded scripts
.\.venv\Scripts\python.exe -m pytest -q -rs
.\.venv\Scripts\python.exe scripts\replay_scenarios.py
git diff --check
```

For security-sensitive changes, also run the available dependency and static
security tools. If a tool is unavailable, record that fact without installing a
large new toolchain unless installation is clearly safe and local.

### Step F — Commit discipline

- Run `git status --short`.
- Stage exact files only.
- Inspect `git diff --cached --stat` and `git diff --cached --check`.
- Use a concise conventional commit message.
- Never include secrets, `.env`, broad generated files, or unrelated dirty files.

### Step G — Deploy runtime changes

- Push only after all local gates pass.
- Wait for `.github/workflows/deploy-function-app.yml` to finish.
- Treat a workflow warning differently from a failed deployment.
- If deployment fails, inspect the job log, fix forward, rerun local gates, and
  deploy again. Do not roll back with destructive Git commands.

Documentation-only changes do not require an otherwise unnecessary production
deployment unless they must be committed to preserve the overnight record.

### Step H — Verify production

For every runtime batch:

1. Run `/healthz` and `/api/status`.
2. Exercise the changed endpoint with a non-sensitive request.
3. Verify expected response headers and error behavior.
4. Generate and verify a signed packet if packet behavior changed.
5. Verify resume/diff/offline behavior if continuity changed.
6. Confirm deployed HTML/JavaScript contains any new UI control.
7. Query Application Insights for new `http_request_failed` traces.
8. Record exact pass/fail counts and the deployment run URL here.

### Step I — Close the batch

- Mark completed checkboxes.
- Add an entry to the execution log.
- Note what remains unverified.
- Continue only if the next task is independent and safe.

---

## 5. P0 work — prove the current implementation is internally consistent

### P0.1 Build a single machine-readable readiness report

Goal: one command should summarize local tests, scenario replay, static checks,
source freshness, source conflicts, live status, deployed commit, and the latest
deployment workflow without contacting a person or invoking paid generative work.

- [x] Decide whether to extend `scripts/final_live_smoke.py` or add a separate
  `scripts/readiness_report.py` so the existing evidence contract is not broken.
- [x] Include source commit and dirty-worktree disclosure.
- [x] Include Python test totals and expected skip reason.
- [x] Include JavaScript syntax result.
- [x] Include scenario replay totals.
- [x] Include program freshness totals.
- [x] Include source conflict totals.
- [x] Include packet generation, signature verification, source diff, handoff,
  and signed snapshot checks.
- [x] Include surge-mode deterministic transformation.
- [x] Include deployed UI token checks.
- [x] Include Application Insights query outcome when Azure CLI is authenticated.
- [x] Clearly separate local, deployed, simulated, and human evidence.
- [x] Ensure the script never prints secrets or full phone numbers.
- [x] Add unit tests for report parsing and exit status.
- [x] Run it locally and against production.

Acceptance criteria:

- One command returns nonzero on any required failure.
- Output states exactly which checks are local versus live.
- No call, SMS, or paid model operation occurs.
- The report identifies the commit it actually tested.

### P0.2 Prevent regression of the Azure Functions request-state defect

- [x] Add a host-safe surge-state fallback.
- [x] Add a regression test that constructs a request without middleware state.
- [x] Add an endpoint-level test proving `/api/surge/status`, `/api/navigate`, and
  `/api/transform` succeed if the ASGI host does not preserve `request.state`.
- [x] Document the Azure Functions adapter behavior in a short code comment or
  architecture note, without overstating that all adapters behave this way.

Acceptance criteria:

- The regression fails against commit `66d25d4` and passes against `e62eda8`.
- Production navigation and surge endpoints return HTTP 200.

### P0.3 Validate every new API contract

- [x] Add TestClient coverage for `/api/programs/freshness`.
- [x] Add TestClient coverage for `/api/source-conflicts`.
- [x] Add TestClient coverage for `/api/chaos/evaluate`.
- [x] Add TestClient coverage for `/api/scenarios/replay`.
- [x] Add TestClient coverage for `/api/surge/status`.
- [x] Add TestClient coverage for `/api/packet/diff/{code}`.
- [x] Add TestClient coverage for `/api/packet/offline/{code}`.
- [x] Add TestClient coverage for `/api/offline/verify`.
- [x] Verify 404 behavior for expired or unknown recovery codes.
- [x] Verify malformed snapshot behavior returns a bounded 400 response.
- [x] Verify unknown chaos modes are ignored rather than executed.
- [x] Verify access preferences reject or ignore unknown values deterministically.

Acceptance criteria:

- Contract tests assert response shape, status code, and safety behavior.
- Tests do not depend on Azure credentials.

---

## 6. P0 work — strengthen source safety

### P0.4 Program-record schema validation

- [x] Define required fields for every program record:
  `id`, `name`, `agency`, `needs`, `eligibility`, `apply_url`, `source_url`,
  `source_excerpt`, `last_verified`, `expiration_date`, `disaster_id`, and
  `review_interval_days`.
- [x] Validate uniqueness of program IDs.
- [x] Validate `last_verified` and non-null expiration values as ISO dates.
- [x] Treat `expiration_date: null` as explicitly non-expiring, not missing.
- [x] Validate HTTPS for external apply/source URLs, while allowing deliberate
  `tel:` emergency links.
- [x] Validate source and apply domains against a reviewed allowlist.
- [x] Validate that freshness metadata is included in recommendation output.
- [x] Fail tests when a new record omits review metadata.

Acceptance criteria:

- Every checked-in record passes schema validation.
- A malformed fixture fails with a precise field-level reason.

### P0.5 Source freshness behavior

- [x] Test current, old, expired, missing-date, invalid-date, and future-date cases.
- [x] Decide and document how future `last_verified` dates are handled.
- [x] Ensure stale recommendations remain visible only with a prominent caveat or
  are routed to human verification according to risk.
- [x] Ensure a stale record cannot retain a `Strong match` label.
- [x] Ensure the API exposes the reason and review interval.
- [x] Ensure the UI has readable current/stale labels in normal, high-contrast,
  large-text, and low-data modes.

Future-date policy: a `last_verified` date after the injected UTC calendar date is
treated as stale with `future_last_verified`; it cannot establish freshness and
routes matched recommendations to source review. It is never silently clamped to
the current date.

Acceptance criteria:

- Staleness is deterministic and time-zone independent.
- Tests use an injected date rather than relying on the wall clock.

### P0.6 Source conflict behavior

- [x] Add conflict fixtures for deadlines, phone numbers, eligibility conditions,
  and program-open/program-closed status.
- [x] Normalize only fields that are safe to compare; never use fuzzy similarity
  to decide which authoritative claim wins.
- [x] Ensure identical values from two sources are not treated as a conflict.
- [x] Ensure conflicting values set `conflict_detected: true`.
- [x] Ensure conflict output includes both sources and both values.
- [x] Ensure a conflicted recommendation routes to human verification.
- [x] Ensure the UI displays a visible conflict warning rather than a normal
  confidence badge.
- [x] Ensure packet signing covers the conflict result.

Acceptance criteria:

- No conflict is silently resolved.
- Synthetic conflict tests pass without changing the production dataset.

---

## 7. P1 work — evidence and contradiction coverage

### P1.1 Recommendation evidence completeness

- [x] Assert every rendered recommendation contains a non-empty rule.
- [x] Assert every recommendation references an existing reviewed source record.
- [x] Assert every source excerpt is non-empty and bounded in length.
- [x] Assert every recommendation includes a review date and confidence caveat.
- [x] Ensure evidence text is escaped before HTML rendering.
- [x] Ensure direct links use `noopener` and the reviewed destination.
- [x] Add a test proving Foundry explanation text cannot replace the deterministic
  matching rule or source excerpt.
- [x] Add an API contract version for evidence trace fields if needed.

Acceptance criteria:

- A recommendation cannot be emitted without its auditable trace.

### P1.2 Contradiction detector expansion

- [ ] Cover wrong jurisdiction.
- [ ] Cover wrong disaster ID.
- [ ] Cover wrong deadline.
- [ ] Cover wrong phone number.
- [ ] Cover an action whose `source_id` is absent.
- [ ] Cover an eligibility explanation that asserts a condition absent from the
  structured record.
- [ ] Cover negation changes such as `may qualify` → `will qualify`.
- [ ] Cover historical/current status inversion.
- [ ] Cover channel-only omission and channel-only insertion.
- [ ] Ensure detected contradictions invalidate packet verification.
- [ ] Ensure failures return a bounded diagnostic without exposing internal data.

Acceptance criteria:

- All important structured fields are checked against every compiled channel.
- The detector never changes a value; it only passes, withholds, or escalates.

### P1.3 Property-style and mutation tests

- [ ] Generate mutations of locked values across web, SMS, voice, and offline.
- [ ] Mutate one field at a time and verify detection.
- [ ] Verify harmless formatting changes do not produce false contradictions.
- [ ] Verify recomputing a channel hash does not bypass the packet signature.
- [ ] Keep the mutation count bounded so the full suite remains fast.

Acceptance criteria:

- Mutations demonstrate that both field checks and cryptographic checks matter.

---

## 8. P1 work — offline, continuity, and diffing

### P1.4 Offline snapshot verifier

- [ ] Add a test that exports a production-style RS256 fixture with a public JWK.
- [ ] Verify the fixture entirely without network access.
- [ ] Tamper with a channel and prove verification fails.
- [ ] Tamper with a source and prove verification fails or clearly explain which
  source material is informational versus cryptographically covered.
- [ ] Verify malformed JSON produces a safe, useful error.
- [ ] Make the command output suitable for a demo screenshot.
- [ ] Clearly state that the local HMAC development mode cannot publish its shared
  secret and therefore is not independently verifiable.
- [ ] Keep the production private key in Key Vault; never export it.

Acceptance criteria:

- A downloaded production snapshot can be checked offline with only public data.

### P1.5 Packet diff semantics

- [ ] Test deadline changes.
- [ ] Test program closure/opening status changes.
- [ ] Test snapshot timestamp changes.
- [ ] Test source hash changes.
- [ ] Test no-change behavior.
- [ ] Ensure diffs do not compare volatile packet IDs, recovery codes, or creation
  timestamps as policy changes.
- [ ] Ensure resumed UI clearly distinguishes `no reviewed change` from `unable to
  compare`.
- [ ] Ensure a changed authoritative field routes the user to reconfirm current help.

Acceptance criteria:

- Diffs show exact meaningful changes and avoid noise from regenerated identifiers.

### P1.6 Continuity privacy and expiry

- [ ] Confirm names, exact addresses, SSNs, bank data, document content, and phone
  numbers never enter a stored packet.
- [ ] Confirm sensitive handoff reasons remain reduced to a boolean/private-review
  indicator.
- [ ] Confirm access preferences are non-medical labels only.
- [ ] Confirm already-tried steps come from a constrained list, not free text.
- [ ] Test code normalization and expiration behavior.
- [ ] Test unknown and expired code responses.
- [ ] Verify Azure Table entities use the documented 24-hour expiration contract.

Acceptance criteria:

- Continuity preserves useful state without becoming a shadow case file.

---

## 9. P1 work — chaos and surge behavior

### P1.7 Chaos dashboard contracts

For each mode, verify API response, visible UI result, and named fallback:

- [ ] Foundry down → deterministic rules and reviewed copy.
- [ ] Translator down → verified English plus interpreter/211 path.
- [ ] Maps down → local CAP geometry and text location result.
- [ ] Stale source → visible warning and human verification.
- [ ] Bad translation → segment withheld; exact English preserved.
- [ ] No network → cached shell and explicit offline snapshot.
- [ ] Multiple simultaneous modes produce a stable ordered result.
- [ ] Unknown modes produce no arbitrary execution.
- [ ] Simulations do not mutate provider configuration or stored data.

Acceptance criteria:

- Every simulated failure has a deterministic, explainable response.

### P1.8 Surge-mode correctness

- [ ] Test boundary at threshold minus one, threshold, and threshold plus one.
- [ ] Test event-window expiry.
- [ ] Test forced surge configuration.
- [ ] Confirm thread safety of the in-process counter.
- [ ] Confirm deterministic matching always remains available.
- [ ] Confirm optional AI explanations are disabled.
- [ ] Confirm optional maps are skipped in the citizen UI.
- [ ] Confirm deterministic/cached transformations remain safe.
- [ ] Confirm response header declares operating mode.
- [ ] Document that the counter is instance-local and not a distributed global
  rate limiter; do not call it one.
- [ ] If feasible without new infrastructure, rename UI/docs to `surge signal` or
  `graceful degradation mode` wherever `rate limit` would overstate the design.

Acceptance criteria:

- The system degrades optional work before core routing.
- Documentation accurately describes the process-local limitation.

---

## 10. P1 work — accessibility and browser behavior

### P1.9 Access preference compilation

- [ ] Test each preference independently.
- [ ] Test multiple preferences together.
- [ ] Ensure unknown preferences are ignored deterministically.
- [ ] Ensure `voice_preferred` does not automatically place a call.
- [ ] Ensure `relay_service` exposes 711 without hiding 911 or 211.
- [ ] Ensure `low_bandwidth` suppresses optional maps/model calls.
- [ ] Ensure `large_text` applies without breaking the results layout.
- [ ] Ensure `screen_reader` output uses meaningful headings and button labels.
- [ ] Ensure preferences are included in the handoff only as access preferences,
  not inferred diagnoses.

Acceptance criteria:

- The same signed facts compile into a presentation appropriate to the selected
  non-sensitive preferences.

### P1.10 Static accessibility checks

- [ ] Verify every form control has an associated label.
- [ ] Verify keyboard focus indicators remain visible.
- [ ] Verify dialogs have close controls and meaningful names.
- [ ] Verify status/toast updates use appropriate live regions.
- [ ] Verify color is not the only stale/conflict/failure signal.
- [ ] Verify touch targets remain reasonable on narrow screens.
- [ ] Verify reduced-motion mode disables nonessential animation.
- [ ] Verify print output does not omit the essential action plan.
- [ ] Run any already-installed automated accessibility checker if available.

Do not claim WCAG certification from automated checks alone.

### P1.11 Front-end resilience

- [ ] Verify JavaScript syntax.
- [ ] Verify the service worker still caches required shell assets.
- [ ] Verify offline save/open/remove behavior.
- [ ] Verify signed JSON download behavior.
- [ ] Verify stale-source and conflict labels render safely.
- [ ] Verify evidence excerpts and rules are HTML escaped.
- [ ] Verify recommendation details work with keyboard activation.
- [ ] Verify resume displays source-diff status.
- [ ] Verify the site remains useful when Azure Maps SDK fails to load.

Acceptance criteria:

- No essential action depends exclusively on an optional third-party script.

---

## 11. P1 work — contact-center handoff quality

### P1.12 Structured handoff contract

- [ ] Confirm JSON contains location at the approved precision.
- [ ] Confirm needs are broad categories.
- [ ] Confirm already-tried steps are constrained values.
- [ ] Confirm relevant programs use stable IDs and readable names where needed.
- [ ] Confirm unresolved ambiguity is explicit.
- [ ] Confirm urgency is explicit.
- [ ] Confirm private reasons are omitted.
- [ ] Confirm packet signature is checked before handoff output.
- [ ] Confirm the human-readable copied version matches the JSON fields.
- [ ] Add a test that no sensitive-field name or value appears in handoff output.

Acceptance criteria:

- A caseworker can understand the state without asking the resident to repeat the
  entire story, while the navigator still avoids storing a sensitive case file.

### P1.13 Phone software-path verification

No real call may be placed overnight. Perform software-only verification:

- [ ] Opening prompt is concise and identifies automation.
- [ ] Immediate danger instruction says to hang up and call 911.
- [ ] Key `1` reads next steps and historical limitation.
- [ ] Key `2` protects sensitive documents and gives alternatives.
- [ ] Key `#` explains the protocol.
- [ ] Key `9` repeats choices.
- [ ] Key `0` provides 211/711 instructions and ends the call.
- [ ] Unsupported keys reprompt safely.
- [ ] Recovery code and phone numbers are spoken digit by digit.
- [ ] Consent and allowlist validation remain fail-closed.
- [ ] Callback signatures reject tampering.
- [ ] No branch claims to transfer to a government representative.

Acceptance criteria:

- Every software branch is covered by deterministic unit tests.
- Human audibility remains explicitly unverified.

---

## 12. P2 work — security, privacy, and operational hygiene

### P2.1 Security checks

- [ ] Run the existing dependency audit command documented by the project.
- [ ] Run the existing Bandit/static-security command.
- [ ] Search tracked files for accidental secrets or connection strings without
  printing secret values into the transcript.
- [ ] Confirm callback signature comparison remains constant-time.
- [ ] Confirm user-provided URLs are never fetched server-side.
- [ ] Confirm outbound application domains are allowlisted or validated.
- [ ] Confirm external links use `noopener`.
- [ ] Confirm error responses do not expose stack traces.
- [ ] Confirm CORS configuration is accurately documented; if wildcard CORS is
  retained for the demo, name it as a production hardening item.
- [ ] Confirm rate/surge controls cannot become an unbounded memory structure.

Acceptance criteria:

- No medium/high static finding at the project's documented threshold.
- No known dependency vulnerability at the time of the run, or an explicit
  documented exception with impact and mitigation.

### P2.2 Telemetry privacy

- [ ] Confirm request bodies are not logged.
- [ ] Confirm phone numbers are not logged.
- [ ] Confirm recovery codes are not logged in normal route messages.
- [ ] Confirm exact address and coordinates are absent from handoff telemetry.
- [ ] Confirm exception logging records exception type rather than secrets.
- [ ] Query recent production telemetry for failures after each deployment.

Acceptance criteria:

- Operational evidence is useful without becoming resident data collection.

### P2.3 Deployment reproducibility

- [ ] Confirm the workflow checks out the exact pushed commit.
- [ ] Confirm dependencies install under Python 3.12.
- [ ] Confirm `.funcignore` excludes tests, decks, local databases, `.env`, and
  other non-runtime material.
- [ ] Confirm new runtime modules and scenario data are included in the package.
- [ ] Confirm the deployed UI token check matches the pushed commit.
- [ ] Record workflow annotations separately from errors.
- [ ] Note the GitHub Node 20 action deprecation warning as maintenance, not a
  current deployment failure.

Acceptance criteria:

- A clean checkout of `main` can produce the deployed package.

---

## 13. P2 work — performance evidence

### P2.4 Local performance characterization

- [ ] Measure deterministic navigation latency over a bounded repeat count.
- [ ] Measure packet creation and verification latency.
- [ ] Measure scenario replay duration.
- [ ] Measure offline snapshot generation and verification duration.
- [ ] Record environment and sample size.
- [ ] Avoid implying production throughput from local results.

### P2.5 Bounded production read-path probe

- [ ] Use only safe GETs and non-sensitive packet operations.
- [ ] Keep concurrency and request counts within the project's established bounds.
- [ ] Record p50, p95, HTTP failures, and cold-start behavior.
- [ ] Avoid speech, Foundry, Translator, calls, and SMS unless a test explicitly
  requires an already-cached/deterministic path.
- [ ] Inspect telemetry after the probe.
- [ ] Do not call this a load test or production capacity result.

Acceptance criteria:

- Evidence is labeled a bounded probe and includes its limitations.

---

## 14. P2 work — documentation and claim consistency

### P2.6 Update stale counts and commit references

The existing handoff/TODO documents predate the reliability deployment and still
mention 200 tests and commit `3573de1`. Because they are pre-existing dirty files,
do not broadly overwrite them. If the user-authored changes can be preserved:

- [ ] Update test count to the final verified count.
- [ ] Update current production commit.
- [ ] Add the new reliability features succinctly.
- [ ] Update production smoke totals and timestamps.
- [ ] Preserve all unrelated edits exactly.
- [ ] Review the staged diff line by line before committing.

If overlap is ambiguous, mark this item `BLOCKED` and leave the files untouched.

### P2.7 Claim audit

Search README, docs, deck source material, and UI copy for contradictions:

- [ ] No claim that 211 transfer is implemented.
- [ ] No claim that SMS delivered.
- [ ] No claim that all phone branches were human-tested.
- [ ] No claim of Virginia data residency.
- [ ] No claim that an NWS alert carries the project's signature.
- [ ] No claim of live-current DR-4831-VA application availability.
- [ ] No claim of native-speaker validation.
- [ ] No claim of distributed rate limiting.
- [ ] No claim of measured contact-center savings.
- [ ] No stale test count or deployment commit in submission-facing copy.

Acceptance criteria:

- Every important claim is either supported by evidence or labeled as a limit,
  simulation, planned integration, or historical replay.

### P2.8 Demo-path documentation

- [ ] Add the new freshness badge to the walkthrough.
- [ ] Add recommendation evidence expansion.
- [ ] Add the packet provenance graph.
- [ ] Add one chaos simulation with visible fallback.
- [ ] Add saved-packet diff or signed JSON export if time permits.
- [ ] Keep the demonstration within the target duration.
- [ ] Do not crowd out the resident story with infrastructure detail.

Acceptance criteria:

- The demo proves trust and resilience in a visible, understandable sequence.

---

## 15. P3 stretch work — only after every higher-priority autonomous item

Do not begin these while P0 or P1 tasks remain.

### P3.1 OpenAPI examples

- [ ] Add bounded example requests/responses for the new endpoints.
- [ ] Ensure examples contain no real phone number, recovery code, or secret.
- [ ] Verify `/docs` renders them.

### P3.2 More replay scenarios

- [ ] Source conflict.
- [ ] Stale source.
- [ ] Wrong county contradiction.
- [ ] Accessibility plus low bandwidth.
- [ ] Immediate danger.
- [ ] Fraud concern.
- [ ] No applicable historical snapshot.
- [ ] Expired continuity code.

### P3.3 Developer ergonomics

- [ ] Add one documented command for the complete safe readiness suite.
- [ ] Keep Windows PowerShell commands working.
- [ ] Keep CI/Linux commands working.
- [ ] Avoid adding a JavaScript build pipeline to the no-build front end.

---

## 16. Explicit human/external blockers — do not retry overnight

Mark these as pending without repeatedly probing or attempting workarounds.

| Blocker | Why autonomous work must stop |
|---|---|
| Real handset walkthrough | Requires a person to answer and assess clarity |
| Live 211 transfer | Requires product decision, telephony support, authorization, and human testing |
| SMS delivery | Requires a paid/approved sender |
| Copilot Studio publication | Requires tenant admin/license/capacity |
| Native-speaker validation | Requires qualified human reviewers |
| Final video recording | Requires visible/user-controlled presentation and narration |
| Competition submission | External publication must remain user-controlled |
| Agency privacy/security approval | Requires organizational governance |
| Measured call-center impact | Requires partner baseline and pilot data |

---

## 17. Stop conditions

Stop the current batch immediately if any of these occur:

- Tests reveal a safety regression that cannot be fixed confidently in the same run.
- Production health, packet verification, continuity, or signing fails.
- A change would require a secret, payment, admin approval, or human judgment.
- The only available fix would overwrite or discard user-authored changes.
- Git history diverges unexpectedly from `origin/main`.
- A deployment fails repeatedly for the same external reason.
- Azure reports quota, billing, policy, or service-health issues requiring the user.
- The remaining tasks are all human/external blockers.

When stopping:

1. Leave the repository in a tested, understandable state.
2. Do not mark incomplete work complete.
3. Record the exact failure and attempted evidence in the execution log.
4. Notify the user only if action is required, a deployment failed, or a meaningful
   milestone was reached.

---

## 18. Final completion criteria

The autonomous overnight run is complete when all of the following are true:

- [ ] All executable P0 items are complete.
- [ ] All executable P1 items are complete or explicitly blocked.
- [ ] Full local suite passes with only documented expected skips.
- [ ] Scenario replay passes.
- [ ] Security/static checks pass or have documented exceptions.
- [ ] Latest runtime commit deploys successfully.
- [ ] Broad live smoke passes.
- [ ] Reliability live smoke passes.
- [ ] Production telemetry shows no new hidden request failures.
- [ ] Claims accurately distinguish local, live, simulated, and human evidence.
- [ ] No call or SMS was sent.
- [ ] No unrelated user changes were committed.
- [ ] This document contains a final summary, final commit, deployment URL, exact
  test totals, remaining blockers, and the next action for the user.

---

## 19. Evidence ledger

Add rows; do not replace prior evidence.

| Time ET | Scope | Commit | Result | Evidence / limitation |
|---|---|---|---|---|
| 2026-09-25 00:33 | Production deployment | `e62eda8` | PASS | GitHub Actions run `36094766717`; Azure Functions deployment completed |
| 2026-09-25 00:33 | Full local tests | `e62eda8` | PASS | 216 passed; 1 expected fixture skip (`swap_road` has no eligible segment) |
| 2026-09-25 00:33 | Broad live smoke | `e62eda8` | PASS | 15/15; no call, SMS, or paid generative transformation |
| 2026-09-25 00:33 | Reliability live smoke | `e62eda8` | PASS | 10/10; freshness, conflicts, chaos, replay, evidence, diff, snapshot, surge, SNAP route, UI |
| 2026-09-25 00:34 | Surge transformation | `e62eda8` | PASS | Seven safe segments; `provider_mode=surge-deterministic` |
| 2026-09-25 00:34 | Production telemetry | `e62eda8` | PASS | No `http_request_failed` traces after final deployment |
| 2026-09-25 02:48 | Program schema local gates | `9af8601` | PASS | 248 passed, 1 expected fixture skip; JavaScript/Python syntax, whitespace, and 4/4 replay passed |
| 2026-09-25 02:48 | Program schema deployment | `9af8601` | PASS | GitHub Actions run `36104289466`; Azure Functions deployment completed in 1m35s |
| 2026-09-25 02:48 | Program schema live readiness | `9af8601` | PASS | All required readiness checks passed; 10/10 program records current, 5 navigation recommendations carried evidence/freshness, signed snapshot verified locally and on server |
| 2026-09-25 02:48 | Production telemetry | `9af8601` | PASS | No `http_request_failed` traces since deployment; Application Insights ingestion lag remains a limitation |
| 2026-09-25 03:47 | Freshness local gates | `cfe7b0b` | PASS | 257 passed, 1 expected fixture skip; injected-date current/old/expired/missing/invalid/future cases and stale escalation passed |
| 2026-09-25 03:47 | Freshness deployment | `cfe7b0b` | PASS | GitHub Actions run `36109240184`; Azure Functions deployment completed in 1m24s |
| 2026-09-25 03:47 | Freshness live readiness | `cfe7b0b` | PASS | All required readiness checks passed; 10 records exposed reason codes/as-of/review interval and all were current; stale warning/accessibility CSS tokens deployed |
| 2026-09-25 03:47 | Production telemetry | `cfe7b0b` | PASS | Zero `http_request_failed` traces since deployment; ingestion-delay limitation applies |
| 2026-09-25 04:50 | Conflict local gates | `e73f285` | PASS | 265 passed, 1 expected fixture skip; four conflict classes, exact-value/source preservation, human routing, and signed-packet mutation passed |
| 2026-09-25 04:50 | Conflict deployment | `e73f285` | PASS | GitHub Actions run `36114824773`; Azure Functions deployment completed in 1m36s |
| 2026-09-25 04:50 | Conflict live readiness | `e73f285` | PASS | All required readiness checks passed; production conflict endpoint returned 200/zero conflicts, five recommendations exposed conflict metadata, six warning/style tokens deployed |
| 2026-09-25 04:50 | Production telemetry | `e73f285` | PASS | Zero `http_request_failed` traces since deployment; ingestion-delay limitation applies |
| 2026-09-25 05:48 | Evidence local gates | `4e4be59` | PASS | 270 passed, 1 expected fixture skip; JavaScript/Python syntax, whitespace, and 4/4 replay passed |
| 2026-09-25 05:48 | Evidence deployment | `4e4be59` | PASS | GitHub Actions run `36120163123`; Azure Functions deployment completed in 1m25s |
| 2026-09-25 05:48 | Evidence live readiness | `4e4be59` | PASS | All required readiness checks passed; five recommendations used `recommendation-evidence-v1`, required fields matched reviewed records, maximum live excerpt was 99 characters, operational headers and deployed escaping/`noopener` contracts passed |
| 2026-09-25 05:48 | Production telemetry | `4e4be59` | PASS | Zero `http_request_failed` traces since 09:45Z; Application Insights ingestion lag remains a limitation |

---

## 20. Execution log

Append concise entries in this format:

```text
### YYYY-MM-DD HH:MM ET — Batch name

- Starting state:
- Changes:
- Local verification:
- Deployment:
- Live verification:
- Telemetry:
- Files committed:
- Commit:
- Remaining limitation:
- Next task:
```

### 2026-09-25 00:35 ET — Overnight plan initialized

- Starting state: production commit `e62eda8`; 216 local tests passed; production
  smoke and reliability checks green.
- Changes: created this autonomous execution plan.
- Local verification: not applicable to documentation-only file.
- Deployment: not required.
- Live verification: existing evidence recorded above.
- Telemetry: no request failures after the final surge-state fix.
- Files committed: none at initialization.
- Commit: none.
- Remaining limitation: human/external blockers remain excluded.
- Next task: P0.1 machine-readable readiness report.

---

### 2026-09-25 00:51 ET — Readiness report and endpoint contracts

- Starting state: main/origin/main at e62eda8; original dirty files preserved.
- Changes: added standalone scripts/readiness_report.py and 26 tests; malformed
  nested offline snapshot fields now return a bounded 400 instead of 500.
- Local verification: 242 passed, one expected swap_road skip; JavaScript syntax,
  Python compile, diff whitespace, and 4/4 scenario replay passed. JUnit parsing
  fails on unexpected skips. No raw subprocess diagnostics or API bodies are
  copied into the report.
- Regression evidence: historical main modules loaded without HTTP middleware:
  66d25d4 returned [500,500,500]; e62eda8 returned [200,200,200] for surge/status,
  navigate, transform. FastAPI's own exit-stack middleware was retained.
- Deployment: pending scoped commit and workflow.
- Live verification: baseline live packet generation, RS256 verification, resume,
  handoff, source diff, downloaded public-key snapshot verification, deterministic
  transformation (7 safe segments), and 5/5 UI tokens passed.
- Telemetry: initial 30-minute query included five failures from 04:28:38–04:28:54Z,
  before e62eda8 deployed. Query since 04:48:21Z returned zero failures. The report
  now anchors telemetry to its own start time; ingestion delay is disclosed.
- Security: pip-audit requirements.txt found no known vulnerabilities. Bandit
  -r api grounded -ll reported one pre-existing medium/low-confidence B608 at
  grounded/store.py:175. The only substitution is int(limit), so SQL syntax cannot
  be injected; this is a documented exception, not a clean static scan.
- Files intended for commit: api/main.py, scripts/readiness_report.py,
  tests/test_readiness_report.py, tests/test_reliability_endpoints.py,
  OVERNIGHT_EXECUTION.md, grounded_eval/results/overnight_local_readiness.json,
  grounded_eval/results/overnight_readiness.json.
- Remaining limitation: the deployed SHA is workflow-reported, not attested by a
  runtime endpoint. Expired-code endpoint tests mock the store's None contract;
  storage expiry implementation is covered by separate continuity tests. Human
  evidence remains unverified. New navigation/chaos live probes await next run.
- Next task: deploy and verify malformed snapshot response, then P0.4 schema.

---

### 2026-09-25 02:48 ET — Reviewed program schema enforcement

- Starting state: main/origin/main at bb424b4; all original dirty and untracked
  files preserved and excluded from staging.
- Changes: added a deterministic program-record validator with required fields,
  unique IDs, strict ISO dates, explicit nullable expiration, positive review
  intervals, HTTPS/credential checks, an exact reviewed-domain allowlist, and an
  exact `tel:911` emergency allowlist. Navigation, freshness, and conflict routes
  now load only a validated catalog and fail closed on malformed review metadata.
- Local verification: 248 passed and one expected `swap_road` fixture skip;
  JavaScript syntax, Python compilation, diff whitespace, and 4/4 scenario replay
  passed. Malformed fixtures return precise field/code diagnostics.
- Security: `pip-audit -r requirements.txt` found no known vulnerabilities.
  Bandit reported zero high findings, two pre-existing medium findings (B608 on
  integer-bounded Cosmos TOP syntax and B314 on parsing locally generated JUnit)
  and 19 pre-existing low findings; this batch introduced none.
- Deployment: GitHub Actions run 36104289466 succeeded for 9af8601 in 1m35s.
- Live verification: bounded readiness passed health, status, operational headers,
  freshness, source conflicts, deterministic navigation evidence, chaos fallbacks,
  packet generation, RS256 verification, resume, handoff, unchanged source diff,
  signed snapshot verification, surge transformation, and UI tokens. No call, SMS,
  or paid generative operation was performed.
- Telemetry: no `http_request_failed` traces since 06:45Z; query absence remains
  subject to Application Insights ingestion delay.
- Files committed: api/main.py, api/navigator.py, api/reliability.py,
  tests/test_reliability.py.
- Commit: 9af8601 (`feat: validate reviewed program records`).
- Remaining limitation: runtime has no commit-attestation endpoint; human evidence
  remains unverified. Existing user-authored dirty files remain untouched.
- Next task: P0.5 source freshness behavior, beginning with injected-date edge
  cases and a deterministic policy for future review dates.

---

### 2026-09-25 03:47 ET — Deterministic freshness policy and visible stale routing

- Starting state: main/origin/main at 7cdb9a9 with deployment green; all original
  dirty and untracked files preserved and excluded from staging.
- Changes: freshness now distinguishes missing, invalid, future, overdue, and
  expired records with stable reason codes, an injected UTC date, review due date,
  age, and a prominent caveat. Future review dates fail stale. Any matched stale
  source loses `Strong match` confidence and routes to source review. The citizen
  UI adds explicit warning text and readable normal, high-contrast, large-text,
  and low-data styles without relying on color alone.
- Local verification: 257 passed and one expected `swap_road` fixture skip;
  JavaScript syntax, Python compilation, diff whitespace, and 4/4 scenario replay
  passed. Tests inject 2026-09-30 rather than reading the wall clock.
- Deployment: GitHub Actions run 36109240184 succeeded for cfe7b0b in 1m24s;
  Node 20 action deprecation and future Ubuntu image migration remain warnings,
  not deployment errors.
- Live verification: bounded readiness passed every required check. The freshness
  route returned HTTP 200 with operational headers, 10 records, zero stale records,
  and reason-code/as-of/review-interval fields. Deployed JavaScript and CSS contain
  the stale warning and all four accessibility-mode selectors.
- Telemetry: zero `http_request_failed` traces since 07:45Z; query absence remains
  subject to Application Insights ingestion delay.
- Files committed: api/reliability.py, api/navigator.py, web/app.js,
  web/styles.css, tests/test_reliability.py, tests/test_reliability_endpoints.py,
  tests/test_web_contracts.py.
- Commit: cfe7b0b (`feat: fail stale source records safely`).
- Remaining limitation: production data is current, so stale rendering is proven
  with deterministic fixtures and deployed-token inspection rather than by
  corrupting the production catalog. Human accessibility review remains unverified.
- Next task: P0.6 source conflict behavior with exact synthetic claim fixtures,
  escalation, visible warnings, and packet-signature coverage.

---

### 2026-09-25 04:50 ET — Exact source-conflict detection and escalation

- Starting state: main/origin/main at 4ff2193 with deployment green; all original
  dirty and untracked files preserved and excluded from staging.
- Changes: authoritative claims now compare only an explicit allowlist of deadline,
  phone, eligibility, and program-status fields. Aliases, whitespace/case, strict
  ISO dates, and phone punctuation are normalized deterministically; unsupported
  prose is ignored and no fuzzy winner is chosen. Conflict output preserves both
  raw values, normalized values, source IDs, and source URLs. Affected
  recommendations replace normal confidence with `Source conflict — verify`,
  route to human review, display explicit alerts, and link to the official source
  for verification instead of the application action.
- Local verification: 265 passed and one expected `swap_road` fixture skip;
  JavaScript syntax, Python compilation, diff whitespace, and 4/4 scenario replay
  passed. Synthetic deadline, phone, eligibility, and open/closed fixtures passed.
  A conflict-bearing packet retained a valid original signature but failed overall
  verification, and mutating the signed conflict result invalidated the signature.
- Security: targeted Bandit scan of changed Python modules returned no findings;
  `pip-audit -r requirements.txt` found no known vulnerabilities.
- Deployment: GitHub Actions run 36114824773 succeeded for e73f285 in 1m36s;
  Node 20 action deprecation and future Ubuntu image migration remain warnings,
  not deployment errors.
- Live verification: bounded readiness passed every required check. The conflict
  endpoint returned HTTP 200 with operational headers and zero production
  conflicts. Five recommendations exposed conflict metadata, and deployed
  JavaScript/CSS contained six conflict-warning and accessibility tokens.
- Telemetry: zero `http_request_failed` traces since 08:47Z; query absence remains
  subject to Application Insights ingestion delay.
- Files committed: api/reliability.py, api/navigator.py, web/app.js,
  web/styles.css, tests/test_reliability.py, tests/test_web_contracts.py.
- Commit: e73f285 (`feat: escalate authoritative source conflicts`).
- Remaining limitation: production data intentionally contains no disagreement,
  so visible conflict behavior is proven by deterministic synthetic fixtures and
  deployed-token inspection rather than by altering reviewed production records.
- Next task: P1.1 recommendation evidence completeness and render-safety coverage.

---

### 2026-09-25 05:48 ET — Auditable recommendation evidence contract

- Starting state: main/origin/main at 114ce77 with deployment green; all original
  dirty and untracked files were preserved and excluded from staging.
- Changes: recommendation evidence now has the explicit
  `recommendation-evidence-v1` contract, a deterministic rule, reviewed source ID,
  label, URL, and disaster ID, whitespace-normalized excerpts bounded to 480
  characters, truncation disclosure, review date, confidence, and caveat. Evidence
  generation fails closed when any required field is missing.
- Local verification: 270 passed and one expected `swap_road` fixture skip;
  JavaScript syntax, Python compilation, diff whitespace, and 4/4 scenario replay
  passed. Tests cover every emitted recommendation, bounding and fail-closed
  behavior, endpoint contracts, render escaping, reviewed links, and model-output
  isolation from deterministic evidence.
- Deployment: GitHub Actions run 36120163123 succeeded for 4e4be59 in 1m25s;
  Node 20 action deprecation and future Ubuntu image migration remain warnings,
  not deployment errors.
- Live verification: bounded readiness passed every required check. A separate
  navigation contract probe returned HTTP 200 with operational headers and five
  recommendations; every trace used `recommendation-evidence-v1`, matched its
  recommendation's reviewed source ID and URL, contained all required fields, and
  had an excerpt no longer than 99 characters. Deployed JavaScript retained escaped
  rule, excerpt, review-date, and caveat rendering plus `noopener` links.
- Telemetry: zero `http_request_failed` traces since 09:45Z; query absence remains
  subject to Application Insights ingestion delay.
- Files committed: api/reliability.py, tests/test_reliability.py,
  tests/test_reliability_endpoints.py, tests/test_web_contracts.py.
- Commit: 4e4be59 (`feat: enforce auditable recommendation evidence`).
- Remaining limitation: UI safety was verified with automated source-contract tests
  and deployed-token inspection, not a human browser or accessibility review.
- Next task: P1.2 contradiction detector expansion, beginning with a complete
  inventory of locked structured fields and current channel coverage.

## 21. Final handoff template

Fill this section when the overnight run ends.

### Outcome

- Final production commit:
- Final deployment workflow:
- Final local test result:
- Final scenario replay result:
- Final live smoke result:
- Final reliability result:
- Final security result:
- Production telemetry result:

### Material improvements completed

-

### Remaining human actions

- Real handset walkthrough of `1`, `2`, `#`, `9`, and `0`.
- Record normal and offline demonstrations.
- Submit the competition materials.
- Obtain any desired tenant, language-review, SMS, or agency approvals.

### Honest final limitations

-

### Recommended first action for the user

-
