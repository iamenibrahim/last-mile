# Handoff — Last-Mile Disaster Navigator

**Event:** Microsoft × CCI Innovation Challenge for Virginia, Sep 21–25 2026

**Challenge:** Disaster Assistance Navigator

**State at handoff:** Thu Sep 24 2026, feature-freeze day

**Repository:** `iamenibrahim/rubicon`, private, branch `main`

**Live application:** <https://lmva3fcshw5lauukqapi.azurewebsites.net>
**Current checkpoint:** commit `525d118`; **200 tests pass, 1 intentionally skipped**

The challenge implementation is about **92% complete**, competition readiness is
about **82%**, and agency production readiness is about **52%**. Core product work
is complete. Remaining competition risk is evidence, documentation, presentation,
and human validation—not another major feature.

Read `README.md` for the design, `docs/prompt-coverage.md` for the challenge map,
`grounded_eval/results/LIVE_OPERATIONAL_EVIDENCE.md` for measured results, and
`infra/DEPLOYED.md` for Azure caveats. Some older statements in those documents
still need the corrections listed below.

---

## 1. Product in one paragraph

Last-Mile is a privacy-first disaster-assistance navigator. It asks only questions
that can change the plan, matches location and broad circumstances to reviewed
government guidance, explains why an option fits, lists documents and official
application paths, warns about fraud, and escalates urgent, sensitive, ambiguous,
or high-impact cases to a person. Its differentiator is the **Last-Mile Protocol**:
one authoritative, cryptographically signed Disaster Action Packet is compiled into
matching web, SMS, voice, offline, and caseworker representations. Microsoft Foundry
may simplify supplied facts but cannot invent benefits, alter locked identifiers or
deadlines, or decide eligibility.

The pitch line is:

> One authoritative, signed action packet survives across web, phone, text,
> offline use, and human handoff.

## 2. Current live state

| Capability | State |
|---|---|
| Azure Functions app and both web experiences | **Live** |
| Microsoft Foundry, Phi-4-mini-instruct | **Live and exercised** |
| Translator, Speech, Content Safety, Maps, AI Search | **Live and exercised** |
| Key Vault RS256 packet/manifest signing | **Live and publicly verifiable** |
| Anonymous 24-hour continuity | **Azure Table Storage; survived an app restart** |
| Application Insights and Log Analytics | **Live; request-body-free telemetry** |
| ACS Call Automation | **Live; delivered to a real handset on Sep 24** |
| ACS SMS | **Unavailable: trial number has no SMS capability** |
| Copilot Studio agent package | **Complete; GMU tenant blocks author signup/license** |
| Cosmos DB | **Not deployed and not used** |
| Foundry embeddings | **Unavailable on the student subscription** |

### Real telephone milestone

- ACS trial number: `+1 844-919-7508`, free through Oct 24 2026.
- Verified/allowlisted test recipient: `+1 703-624-0864`.
- First real call was accepted as connection
  `22005c80-64a1-4182-8cbd-985d68532549` with proof `PRF-TRPUX3SK`.
- The recipient confirmed the phone rang and audio played.
- The first script was too dense. Commit `93b0843` shortened the opening, moved
  case details behind key `1`, speaks phone numbers and recovery codes digit by
  digit, and fixed key `9`.
- Commit `525d118` added `#` for a concise explanation of what the demo proves.
- Current keys: `1` next steps, `2` missing documents, `#` demo explanation,
  `9` repeat, `0` human-help instructions.
- The website exposes a consent-gated **Call with Microsoft neural voice** control
  after a signed packet is generated or resumed.
- A second real call should be placed before recording the final demo to validate
  every key on the deployed revision.

## 3. Run and verify locally

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn api.main:app --port 8000
```

Expected result: `200 passed, 1 skipped`. Open <http://127.0.0.1:8000>.
No cloud configuration is required; providers have named deterministic fallbacks.

Useful live checks:

```powershell
Invoke-RestMethod https://lmva3fcshw5lauukqapi.azurewebsites.net/healthz
Invoke-RestMethod https://lmva3fcshw5lauukqapi.azurewebsites.net/api/status
```

## 4. Demonstration path

1. Open `/`, use ZIP `24370`, select Smyth County, temporary housing, and lost
   documents. Point out that only questions capable of changing the plan are asked.
2. Show the signed packet, proof ID, locked facts, official actions, and privacy
   receipt. Switch Web/SMS/Voice/Offline to show one state across channels.
3. Save the plan offline, then resume it using the anonymous `RBX-xxxxx` code.
4. In Alert Clarity Lab, transform the alert, show locked entities, trigger the
   corruption/refusal demonstration, and verify the manifest.
5. Use the website's voice form to request the real Microsoft neural-voice call.
   During the call press `#` to explain the protocol, then `1`, `2`, `9`, and `0`.
6. Show the fraud checker and the official reporting path.
7. Open `/grounded/` and search exact government quotes to demonstrate the
   evidence layer.

Always say that the recovery scenario is historical, the 2024 deadline passed,
and current availability must be reconfirmed with the official agency.

## 5. Architecture map

```text
Authoritative government records
        ↓
Deterministic applicability + safety rules
        ↓
Signed Disaster Action Packet (Key Vault RS256)
        ↓
Web · SMS representation · ACS voice · offline · caseworker handoff
        ↓
Microsoft Foundry / Translator may clarify supplied text
        ↓
Entity, grounding, instruction, negation, entailment, and integrity checks
        ↓
Verified output or explicit abstention
```

Important files:

```text
api/main.py                         FastAPI endpoints and grounded-app mount
api/protocol.py                     action packet, signing, channels, continuity
api/navigator.py                    program matching and escalation rules
api/providers/azure_voice.py        ACS Call Automation and DTMF flow
api/transform.py                    lock → transform → verify → abstain
api/signing.py                      Key Vault RS256 / local fallback
grounded/                           authoritative source and exact-quote pipeline
grounded_eval/                      corruption and multilingual evaluations
copilot/                            prepared Copilot Studio Swagger and instructions
infra/student.bicep                 cost-guarded student Azure deployment
web/                                primary citizen experience
tests/                              200 passing tests, 1 expected skip
```

## 6. Evidence worth quoting

- **80 real NWS alerts**, **1,972 locked entities**, **0 integrity failures**.
- Mechanical-corruption abstention recall **100%** at **7.3% false abstention**.
- Disabling entity locks lets about **2%** of number corruptions escape remaining
  checks. Always call these *mechanical corruption classes*.
- Read-path probe: **40/40 HTTP 200** at concurrency 8; p50 **196 ms**, p95
  **2.35 s**; observed cold `/healthz` **3.72 s**.
- English Foundry cold transformation reduced from roughly **21 s** to a measured
  range of **4.7–12.1 s**; repeated identical requests are transparently cached.
- English verification: **83.3%** of segments; roughly **16.7%** are withheld,
  commonly because the model adds unsupported closing advice.
- Multilingual withholding: Spanish **14.3%**, Arabic **0%**, Dari **14.3%**,
  Tagalog **28.6%** on the bounded live-provider check; zero locked-entity failures
  and zero provider errors. This is not native-speaker validation.
- Dependency audit: no known vulnerabilities. Bandit: no medium/high finding at
  medium-or-higher confidence. Security automation runs on push/PR.
- Real ACS voice delivery is now confirmed by the recipient.

## 7. Hard limits and honest claims

Say these without waiting for a judge to ask:

- **Historical demonstration:** the main recovery case is DR-4831-VA and its
  application deadline has passed. Do not present it as current assistance.
- **Region:** the demo runs in Canada Central because the student subscription
  refuses US regions. Do not claim Virginia data residency. An agency template
  would use `eastus` subject to policy approval.
- **Model:** the student subscription has zero Azure OpenAI quota. The system uses
  Microsoft's Phi-4-mini-instruct. Model choice is a deployment setting.
- **Embeddings:** none are deployed. English uses Foundry entailment; multilingual
  verification uses entity/rule checks and round-trip evidence where available.
- **Voice:** delivered to a real handset. Trial limits are three verified
  recipients, 60 inbound and 60 outbound minutes, and five minutes per call.
- **SMS:** has never delivered and cannot deliver from the trial number. A paid,
  approved sender is required.
- **Copilot Studio:** both live REST tools work, but GMU disabled self-service
  signup. A trial would not permit publishing anyway; an administrator must assign
  author access and licensed capacity or a Microsoft 365 Copilot license.
- **Continuity:** Azure Table Storage, not Cosmos and not temporary SQLite, is the
  deployed store.
- **Trust anchor:** NWS alerts are fetched over TLS and then attested with the
  project's signature. Do not call it an NWS signature.
- **Impact:** no measured call-center savings, abandonment reduction, or
  time-to-assistance result exists yet. Illustrative calculator output is not
  evidence.

## 8. Copilot Studio state

`copilot/last-mile-handoff.swagger.json` already points to the live Function host.
Both tools were exercised directly:

- `GetHandoff` returned a signature-verified packet with actions and boundary text.
- `SearchSourceQuotes` returned exact FEMA sentences with source URLs.

GMU Copilot Studio displays: **"Sign-up was disabled by your admin."** The required
request is Copilot Studio author access plus tenant capacity/user licensing, or an
applicable Microsoft 365 Copilot license. Treat Copilot as externally blocked; do
not spend feature-freeze time trying to bypass tenant policy.

## 9. Remaining work by priority

### P0 — submission blockers

1. Place a second real call and test `1`, `2`, `#`, `9`, and `0` on the deployed
   simplified flow. Record whether each branch was understandable.
2. Update `infra/DEPLOYED.md`, `docs/prompt-coverage.md`, and
   `grounded_eval/results/LIVE_OPERATIONAL_EVIDENCE.md` to remove stale claims that
   voice is untested, continuity is SQLite, or the suite has fewer than 200 tests.
3. Run the final live endpoint/security smoke suite and save the results.
4. Finish the PowerPoint and a 3–5 minute demo script centered on one resident.
5. Record the normal and `LAST_MILE_OFFLINE=1` fallback demonstrations.
6. Upload the video, deck, short description, challenge, and GitHub link to the
   competition project page.
7. Freeze `main`: clean worktree, green deployment/security runs, final tag.

### P1 — high-value human evidence

1. Give three unfamiliar people the app without instruction; record completion
   time, confusion, and task failures.
2. Run NVDA plus keyboard-only and high-contrast walkthroughs.
3. Obtain any available native-speaker review for Spanish, Arabic, Dari, or Tagalog.
4. Capture actual Azure Cost Management spend and label all projections.

### P2/P3 — post-hackathon or externally blocked

- Paid, regulatory-compliant ACS SMS sender.
- Licensed Copilot Studio tenant and Teams publication.
- Current-event operational ingestion and freshness SLA.
- Census B16004 exposure analysis.
- Agency contact-center pilot and economic/outcome measurements.
- US-region agency deployment, formal threat model, privacy impact assessment,
  accessibility certification, penetration test, sustained load test, and DR plan.

## 10. Security and product invariants

Do not weaken these to improve demo output:

- Models never determine eligibility or originate emergency instructions.
- Locked government identifiers, deadlines, places, numbers, phone numbers, and
  URLs must survive byte-for-byte.
- A model may add an escalation but never lower or remove a rule-based escalation.
- Search output must be located verbatim inside a verified government source.
- Damaged or unsupported output is withheld; it is never silently shipped.
- Sensitive handoff reasons, exact coordinates, phone numbers, names, SSNs, bank
  data, immigration status, and documents are excluded from continuity packets.
- Calls and messages require explicit consent and fail closed when providers or
  sender configuration are unavailable.
- The agency—not the system—makes the final eligibility decision.

## 11. Immediate next command sequence

```powershell
git status --short
.\.venv\Scripts\python.exe -m pytest -q
Invoke-RestMethod https://lmva3fcshw5lauukqapi.azurewebsites.net/healthz
Invoke-RestMethod https://lmva3fcshw5lauukqapi.azurewebsites.net/api/status
gh run list --limit 5
```

After verifying the improved phone flow, update the evidence documents, deck, and
video. Do not begin another large feature before the P0 submission artifacts are
complete.
