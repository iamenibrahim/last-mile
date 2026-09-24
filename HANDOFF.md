# Handoff — Last-Mile Disaster Navigator

**Event:** Microsoft × CCI Innovation Challenge for Virginia, Sep 21–25 2026 (virtual)
**Track:** Disaster Assistance Navigator
**State at handoff:** Wed Sep 23 2026, evening. **169 tests pass, 1 skipped.** Azure
is deployed and a Foundry model is live; the app code is not yet published to Azure.
**Feature freeze:** end of Thu Sep 24. Fri Sep 25 is pitch only, no new code.

Read `README.md` for the design rationale, `TODO.md` for what is left, and
`infra/DEPLOYED.md` for the live Azure environment and its caveats. This file is
what the next person needs to pick the work up.

---

## 1. What this is, in one paragraph

A website that tells someone after a disaster whether government help is declared
where they live, how long they have to apply, and what to do next. It answers in
plain language, in their own language, and can read it aloud. Eligibility and
deadlines come from OpenFEMA data, never from a model. Every sentence about a
program is a verbatim, cited quote from FEMA, the eCFR, SBA or SAMHSA. Urgent or
sensitive cases are handed to a human before anything else. It keeps nothing but
the county.

It is built on the **Last-Mile Protocol**: one signed Disaster Action Packet is
compiled into web, SMS, voice and offline forms, so every channel carries the same
locked facts and the same proof id.

## 2. Get it running (Windows, ~5 minutes)

The virtualenv is not in the repo. Recreate it:

```bash
python -m venv .venv && .venv/Scripts/python.exe -m pip install -r requirements-dev.txt
```

```bash
.venv/Scripts/python.exe -m pytest -q
```

Expect `169 passed, 1 skipped`. The skip is `tests/grounded/test_abstention.py`'s
`swap_road` case: the alert it picks has no road number to corrupt. That is expected.

```bash
.venv/Scripts/python.exe -m uvicorn api.main:app --port 8000
```

Open <http://localhost:8000>. No keys or accounts are needed; everything falls back
to local engines. Built with Python 3.12.14.

## 3. Two front ends, one pipeline

| URL | What it is |
|---|---|
| `/` | **Last-Mile Navigator** — the protocol UI: need-first intake, Disaster Action Packet, web/SMS/voice/offline tabs, `RBX-xxxxx` continuity code, alert clarity lab, fraud check |
| `/grounded/` | **Last-Mile Assist** — the evidence-first UI carried over from the earlier build: ZIP → county → cited programs, deadline countdown, per-segment abstention |
| `/grounded/alert.html` | The warning-side alert transformer |

Both are served by the same process. `api/main.py` mounts the grounded app at
`/grounded` and loads its alert store at import, because the Azure Functions ASGI
bridge runs no startup events.

## 4. The demo, in the order it runs

| # | do | you should see |
|---|---|---|
| 1 | `/` with ZIP `24370`, generate the plan | "Which county?" — the ZIP crosses the Smyth/Washington line, so it asks instead of guessing. Then the packet, with the "17 possible / 3 asked / 14 skipped" audit |
| 2 | Switch the Web / SMS / Voice / Offline tabs | Same locked facts and proof id compiled four ways |
| 3 | Alert clarity lab → run the Spanish transform, play the audio | Plain-language output at a lower reading grade |
| 4 | Toggle **Test refusal**, run again | An orange segment: a critical entity was removed, so that segment is withheld, the exact English is shown, and an interpreter is offered. **Pause here — this is the pitch.** |
| 5 | **Verify this result** | Signature and content hash match. Then say the trust-anchor limit out loud (§8) |
| 6 | `/grounded/` with ZIP `24370` → Smyth County | "42 DAYS LEFT TO APPLY" from real OpenFEMA data for DR-4831-VA |
| 7 | `/grounded/api/quotes/search?q=appeal a decision` | Exact sentences from FEMA and the eCFR, each with its source URL |
| 8 | `/api/signing-key` | Which key signs the manifests, and whether anyone else can verify it |

## 5. Where things are

```
api/main.py          all endpoints; mounts the grounded app at /grounded
api/protocol.py      Disaster Action Packet: build, sign, verify, channel compile, continuity codes
api/navigator.py     service matching over need codes
api/transform.py     lock -> transform -> verify -> abstain for alerts
api/verify.py        the four checks; semantic_fidelity uses Foundry embeddings when available
api/signing.py       one signer for manifests and packets: Key Vault RS256, else local HMAC
api/geo.py           Azure Maps geocoding, Census fallback, point-in-polygon
api/providers/       azure_foundry, azure_translator, azure_content_safety, azure_sms, azure_voice, local
grounded/            the real-data pipeline carried over from the earlier build
grounded/sources.py    17 hash-verified source docs + the exact-quote locator
grounded/quote_search.py  Azure AI Search over 449 source sentences; BM25 fallback
grounded/escalation.py    rules are the floor; a model may only ADD a trigger
grounded/fema.py          OpenFEMA declarations, deadlines, 44 CFR 206.112(d) late window
grounded_eval/       corruption injection, metrics, report (grounded_eval/results/REPORT.md)
eval/                the fixture harness + real_alert_corpus passthrough
copilot/             Copilot Studio caseworker agent: swagger tool + setup instructions
infra/               student.bicep / student.json, DEPLOYED.md
data/grounded/       82 cached alerts, 17 sources, OpenFEMA snapshots, gazetteer (7 MB)
tests/ + tests/grounded/   169 tests
```

## 6. Rules that must not be broken — and the test that guards each

| invariant | guarded by |
|---|---|
| No program sentence of our own; every claim is a located quote | `test_every_catalog_quote_is_found_verbatim` |
| Individual Assistance = `ihProgramDeclared OR iaProgramDeclared` | `test_individual_assistance_is_ih_or_ia` |
| Deadline: open → 60-day late window → closed | `test_deadline_windows_follow_the_regulation` |
| A model can add an escalation, never lower or remove one | `test_a_model_cannot_lower_or_remove_an_escalation`, `tests/grounded/test_escalation_classifier.py` |
| The escalation model only ever sees redacted text | `test_the_model_only_sees_redacted_text` |
| Nothing typed is kept or echoed | `test_nothing_typed_survives_into_the_response` |
| A damaged sentence is withheld, never shipped | `test_a_damaged_fraud_warning_is_withheld_not_shipped` |
| A rewritten channel with a recomputed hash still fails the packet signature | `test_rewritten_channel_with_recomputed_hash_still_fails` |
| An RS256 signature verifies with only the published public key | `tests/test_signing.py` |
| Search returns only sentences located verbatim in a verified source | `test_a_search_engine_hit_that_is_not_in_the_source_is_dropped` |

If a change makes one of these fail, the change is wrong — not the test.

## 7. Azure: what is live, and what is not

Deployed 2026-09-23 into `last-mile-student-rg`, `canadacentral`, name prefix `lmva`.
Full detail and every caveat: `infra/DEPLOYED.md`.

| Service | State |
|---|---|
| Azure Functions (`lmva3fcshw5lauukqapi`) | Deployed. **App code not published yet** — the URL 404s |
| Foundry — `last-mile-gpt` = **Phi-4-mini-instruct** | **Live**, verified in the playground |
| Translator (S1), Speech (S0), Content Safety (S0) | Deployed, never called yet |
| Azure AI Search (free tier) | Deployed; the index builds on the first query |
| Azure Maps, Application Insights, Key Vault (RS256 key), Communication Services | Deployed |
| Cosmos DB | **Not deployed** — free tier would not provision |
| Foundry embeddings | **Not possible** — no quota for any embedding model |

**Nothing has run against real Azure endpoints yet.** There is no `.env`, and the
code is not on the Function App, so every local run still uses local fallbacks.
Expect provider bugs on the first keyed run; do that before adding anything else.

### Three Azure limits worth knowing before you promise anything

1. **Zero Azure OpenAI quota.** The Foundry quota page reads `0/0` for every OpenAI
   model, region and deployment type. That is a standing Azure for Students limit.
   Microsoft's own first-party models (Phi) do have quota, which is why the pipeline
   runs on Phi-4-mini-instruct. No embedding model can be deployed at all.
2. **`eastus` is refused** (`RequestDisallowedByAzure`), so this runs in Canada
   Central. **Do not claim Virginia data residency.**
3. **Soft-deleted resources hold their names and free-tier slots for 48 hours.**
   That is why the prefix is `lmva` and why three Cognitive Services accounts are on
   paid tiers.

## 8. Say these out loud in the pitch, unprompted

- **Trust anchor.** NWS alerts are not individually signed. We attest to a payload
  fetched over TLS plus our own signature — never "a verified NWS signature".
- **Model.** It runs on Microsoft's Phi-4-mini-instruct because the subscription has
  no OpenAI quota. Model choice is a deployment parameter, not a code change. This
  is a Microsoft-native story, not an apology.
- **Region.** Canada Central, because Azure refuses US regions here. An agency
  deployment uses `eastus`, Azure's Virginia region.
- **Tiers.** Translator, Speech and Content Safety are pay-per-use, not free tier.
  Demo volume is a fraction of a cent.
- **Corruption numbers** come from five *mechanical* corruption classes. Say
  "mechanical" every time you quote them.
- **The synthetic fixture** in the alert lab is labelled "not an active warning".
- The system **never originates an alert** and **never decides eligibility**.

## 9. Numbers you can quote

From `grounded_eval/results/REPORT.md` and `data/evaluation_report.json`
(`real_alert_corpus`), over **80 real NWS alerts**, using **local** stub engines:

- **1,972** entities locked, **0** integrity failures
- Abstention recall **100%** at **7.3%** false abstention
- With entity locking off, about **2%** of number corruptions get past the other checks
- Median reading grade **8.48 → 6.78**
- **17** hash-verified source documents, **449** sentences indexed, **41** catalog quotes
- **93.75%** of the 80 alerts carry a non-empty `instruction` field — report as a
  finding, not a score

Rerun after any pipeline change:

```bash
.venv/Scripts/python.exe -m grounded_eval.metrics --lang en --limit 200 --ablate
.venv/Scripts/python.exe -m grounded_eval.report > grounded_eval/results/REPORT.md
.venv/Scripts/python.exe -m eval.report
```

Label the engines whenever you quote these. They show the pipeline catches what it
is built to catch; they are not a measure of model quality.

## 10. Keys and configuration

Nothing is required to run. Every variable in `.env.example` is optional and each
upgrades one local fallback to its Azure service. `api/__init__.py` loads `.env` on
start, and skips it under pytest so tests never reach live services.

To set up a local `.env`: paste the Function App's **Environment variables →
Advanced edit** JSON into `azure-settings.txt`, add the Foundry **Key 1** on its own
line, then:

```bash
python scripts/settings_to_env.py
```

Both `azure-settings.txt` and `.env` are gitignored. `GET /api/status` and the header
badge report which engines are live. `LAST_MILE_OFFLINE=1` forces everything local,
for the fallback video.

Leave `AZURE_FOUNDRY_EMBED_MODEL` **empty** — no embedding model exists, and pointing
at one that does not just fails into the fallback.

## 11. What is left, in priority order

See `TODO.md` for the full list. The short version:

1. **Publish the code to the Function App.** Deployment Center is configured for
   GitHub CI/CD; it is waiting on the GitHub **Authorize** button, which grants Azure
   access to the repo. Org `iamenibrahim`, repo `rubicon`, branch `main`.
2. **First run against real Azure**, then re-measure how often each language is
   withheld (es, ar, prs, tl). This is what turns "code exists" into "it works".
3. **Connect the Copilot Studio agent** — `copilot/` is ready and already points at
   the deployed host name.
4. Foundry Evaluations dashboard; the ACS B16004 impact number (needs a free Census key).
5. **Thu night:** update the deck, record the `LAST_MILE_OFFLINE=1` fallback video,
   freeze.

## 12. Known gaps and risks

- **No Azure path has run for real.** Highest-risk item by far.
- **Offline, non-English is mostly withheld.** Correct behaviour for a glossary stub,
  and a weak demo. Translator is deployed; this should improve on the first keyed run.
- **Glossaries and multilingual escalation cues are not native-speaker reviewed.**
  Every file says so.
- **Form labels are English only.** Results are translated; the form is not.
- **No cited domestic-violence hotline.** Abuse cases route to 911, the Disaster
  Distress Helpline and legal aid, all cited. A hotline needs its own captured source.
- **Deadlines are as of the last OpenFEMA fetch.** FEMA extends them, and every
  deadline line says so.
- **FEMA's English and Spanish fraud pages disagree** on the phone line. Present the
  disagreement as the finding; do not pick a side.
- **SMS and voice cannot actually send** until an ACS number is purchased; both are
  fail-closed and off by default.
- **The signing key is per-environment.** Manifests signed locally will not verify on
  Azure and vice versa, unless `MANIFEST_SIGNING_KEY` is shared or Key Vault is used.
- **Cosmos DB is absent**, so the render cache is SQLite in the Functions temp
  directory and does not survive a cold start. Harmless for a demo.
- **The repo is private** (`iamenibrahim/rubicon`). One ported file carries a personal
  email address; swap it for a placeholder before making the repo public.

## 13. Windows and tooling gotchas

- Set `PYTHONIOENCODING=utf-8` before running scripts that print non-ASCII text.
- `uvicorn --reload` sometimes keeps serving a stale static mount after a change to
  `main.py`. Restart the server.
- `fema.gov` and `DisasterAssistance.gov` return 403 to scripts. **Do not try to get
  around that.** To add a FEMA page, capture it in a browser and run
  `python scripts/grounded/ingest_browser_sources.py`, which rejects the file unless
  its hash matches the one computed in the page.
- The Azure portal's template editor will not accept a paste from an automated
  browser; use its **Load file** button.
