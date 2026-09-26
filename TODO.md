# TODO: Microsoft × CCI Innovation Challenge

**Status correction, September 25:** this checklist is historical. Phone
verification and a real voice call were completed September 24; continuity uses
Azure Table Storage. Current technical results and remaining work are in
[`FINAL_TECHNICAL_CHECK.md`](grounded_eval/results/FINAL_TECHNICAL_CHECK.md).
Do not repeat the old phone-setup steps solely because they appear below.

**Today: Thu Sep 24. Feature freeze is tonight.** Fri Sep 25 is pitch only, no new code.

Deployed environment and its caveats: [infra/DEPLOYED.md](infra/DEPLOYED.md).
Measured evidence: [grounded_eval/results/LIVE_OPERATIONAL_EVIDENCE.md](grounded_eval/results/LIVE_OPERATIONAL_EVIDENCE.md).

Legend: ✅ done · 🔒 blocked on you · ⬜ not started

---

## Blocked on you — nothing else moves until these

- 🔒 **A. Verify your phone against the trial number.** Phone numbers →
  `1-844-919-7508` → **Trial details** → **Manage verified phone numbers** →
  Add → `+1 703-624-0864`, US, SMS → Next → enter the passcode Microsoft texts
  you. Three recipients maximum. I cannot do this: the Azure portal renders
  blades in a cross-origin iframe that the browser pane cannot click into, and
  the passcode goes to your handset.

- 🔒 **B. Turn on calling.** Function App `lmva3fcshw5lauukqapi` → Settings →
  Environment variables → App settings:

  | Name | Value |
  |---|---|
  | `CALL_START_ENABLED` | `true` |
  | `AZURE_CALL_FROM_NUMBER` | `+18449197508` |
  | `CALL_ALLOWED_TEST_RECIPIENTS` | `+17036240864` |

  Everything else is already wired: the Function App's managed identity holds
  Contributor on Communication Services, ACS holds Cognitive Services User on
  Speech, and the endpoint, callback URL and voice settings all ship in the
  template. These three are the whole gap.

- 🔒 **C. Copilot Studio access.** Sign in at <https://copilotstudio.microsoft.com>
  with your GMU account. If the tenant allows it, item 3 becomes possible.

- 🔒 **D. Free Census API key** — <https://api.census.gov/data/key_signup.html>.
  Two minutes. Only needed for item 4.

## Mine, the moment A and B land

- ⬜ **1. Place a real automated call.** Confirm
  `azure_communication_services_voice: true`, build a signed Smyth County
  packet, take its `RBX-xxxxx`, POST `/api/calls/start` with consent. Capture
  the call connection id, proof id and Application Insights trace into
  `LIVE_OPERATIONAL_EVIDENCE.md`. This turns "voice is implemented and tested"
  into "voice delivered to a real handset on 2026-09-24".

- ⬜ **2. SMS: not happening.** A trial number has no SMS capability and the
  Try SMS sender list is empty and disabled. Outbound texting needs a purchased
  number, which is a spend decision. Disclose it; do not try to work around it.

- ⬜ **3. Connect the Copilot Studio agent** (needs C): upload
  `copilot/last-mile-handoff.swagger.json` as a REST tool, paste the
  instructions from `copilot/README.md`, publish to Teams.

- ⬜ **4. Compute the impact number** (needs D) from ACS B16004 and the alert
  archive. Do not state a Virginia coverage figure until this run completes.

- ⬜ **5. Foundry Evaluations** on the corruption-test set; screenshot for the
  deck. First to cut.

## Tonight

- ⬜ **6. Update the deck:** one slide per Microsoft service and its job, the
  measured numbers, and the honest limits below.
- ⬜ **7. Record the offline fallback video** with `LAST_MILE_OFFLINE=1`.
- ⬜ **8. Freeze.**

---

## Done

**2026-09-24**

- ✅ **English Foundry transformation: ~21s → ~5s live** (4.68 / 5.09 / 8.29s
  cold at three grades; 0.85s repeat). Keep-alive client, eight workers,
  bounded retry honouring `Retry-After`, and a bounded temperature-0 cache
  whose hits the manifest records as `cached_segments`.
- ✅ **Found and fixed a real defect behind that latency.** Asked for a JSON
  schema, the Phi deployment invented key names *and stripped the brackets off
  the `[[E1]]` sentinels*, failing the entity check and pushing 3 of 7 segments
  onto the local fallback — a third of the "Foundry" demo was not Foundry. Two
  worked examples fixed it; now 0 fallbacks.
- ✅ **English meaning check is real.** Was lexical token overlap, which
  punished simplification for doing its job. Now Foundry reverse entailment:
  does the plain-language output still carry every claim the source made.
  83.3% of segments verified, up from 4/7.
- ✅ `prompt_sha256` hashes the prompt actually in use, not a hand-written
  version string that had stopped tracking it.
- ✅ Established what Communication Services actually permits, and corrected an
  earlier wrong note that claimed no verification step existed.

**Earlier**

- ✅ Azure resources deployed; `last-mile-gpt` = Phi-4-mini-instruct.
- ✅ `grounded` package served at `/grounded`: 80 real NWS alerts, hash-verified
  FEMA/eCFR/SBA/SAMHSA quotes, OpenFEMA deadline rules.
- ✅ Key Vault RS256 signing; public key at `GET /api/signing-key`. Fixed a real
  hole: a rewritten channel with a recomputed hash used to still verify.
- ✅ Foundry escalation classifier that can only add a human handoff, never
  remove one. Azure AI Search, exact quotes only. Azure Maps geocoding.
- ✅ Application Insights, capped at 0.1 GB/day.
- ✅ Continuity moved to **Azure Table Storage**; an `RBX` code survived a real
  Function App restart.
- ✅ Multilingual withholding: es 57.1→14.3%, ar 71.4→0%, prs 57.1→14.3%,
  tl 85.7→28.6%.
- ✅ GitHub Actions continuously deploys `main` to `lmva3fcshw5lauukqapi`.
- ✅ 195 tests pass, 1 skipped. Dependency audit and Bandit clean.

---

## Say these out loud in the pitch, unprompted

- **Region.** Canada Central, because Azure refuses US regions on a student
  subscription. An agency deployment uses `eastus`, Azure's Virginia region, to
  keep residents' data in state — a parameter, not a code change.
  **Do not claim Virginia data residency.**
- **No OpenAI models.** Student subscriptions get zero OpenAI quota, so the
  pipeline runs on **Microsoft's Phi-4-mini-instruct**. Model choice is a
  deployment parameter. This is a *better* Microsoft story, not an apology.
- **No embedding model**, same quota reason. Translation fidelity says so in its
  own output rather than pretending; English uses entailment instead.
- **16.7% of English segments are withheld**, mostly because the model appends
  advice the source never contained and the grounding judge refuses it. That is
  the system working. Say it before a judge finds it.
- **SMS and voice.** Implemented, consent-gated, test-covered. SMS has never
  delivered and cannot from a trial number. Say whether voice has, honestly,
  depending on how item 1 goes.
- **Cosmos DB is not deployed** (would not provision in Canada Central).
  Continuity is Azure Table Storage — not SQLite, not temp disk.
- **Not everything is free tier.** Translator, Speech and Content Safety are
  pay-per-character because soft-deleted accounts hold the free slots.
- **Trust anchor.** NWS alerts are not individually signed. We attest to a
  payload fetched over TLS plus our own signature — not an NWS signature.
- **The corruption numbers** come from five *mechanical* corruption classes.
  Say "mechanical" every time.
- **Repeat demo runs are cache-served.** If you run the same alert twice on
  stage and it returns instantly, that is the cache, and the manifest says so.

## If time runs short

Cut in this order: **5** (Foundry Evaluations), **4** (impact number),
**3** (Copilot agent).

Never cut: **A**, **B**, **1** — a real call is the single most valuable thing
left, and it costs you about three minutes of portal clicking.
