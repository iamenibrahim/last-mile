# TODO: Microsoft × CCI Innovation Challenge

Today: Wed Sep 23, evening. **Feature freeze: end of Thu Sep 24.** Fri Sep 25 is pitch only, with no new code.

Goal: the most Microsoft-native version of the project, with every service doing real work.

Deployed environment and its caveats: [infra/DEPLOYED.md](infra/DEPLOYED.md).

Legend: ✅ done · ⏳ in progress · ⬜ not started

## The one thing blocking everything else

- ⏳ **2. Deploy the two Foundry models.** Nothing AI-powered works until this is done.
  Open the `lmva3fcshw5lauukqfoundry` resource → **Go to Foundry portal** → **Deployments**:
  - `gpt-4.1-mini`, deployment name exactly **`last-mile-gpt`**
  - `text-embedding-3-small` (any name; then set `AZURE_FOUNDRY_EMBED_MODEL` to it)

  If neither model is offered in `canadacentral`, say which ones are and we pick from those.

## You (Azure portal / browser)

- ✅ **1. Deploy the Azure resources.** Done 2026-09-23 into `last-mile-student-rg`, `canadacentral`, prefix `lmva`.
- ⬜ **3. Hand over the keys.** Function App `lmva3fcshw5lauukqapi` → Settings → Environment variables → **Advanced edit**, copy all of it into `azure-settings.txt` in this folder. Add the Foundry resource's **Key 1** on its own line. Never paste keys in chat; `python scripts/settings_to_env.py` turns the file into `.env` and both are gitignored.
- ⬜ **4. Check Copilot Studio access** at <https://copilotstudio.microsoft.com> with your GMU account.
- ⬜ **5. Get a free Census API key** at <https://api.census.gov/data/key_signup.html>. Only needed for item 19.

## Claude (code) — all done

- ✅ **6.** Copilot Studio agent pieces: `GET /api/handoff/{code}`, the swagger tool definition (already pointed at the deployed app), and setup instructions.
- ✅ **7.** Moved the real-data evidence from `hackily` into the `grounded` package, served at `/grounded`: 80 real NWS alerts, hash-verified FEMA/eCFR/SBA/SAMHSA quotes, OpenFEMA deadline rules. Its 116 tests run under `tests/grounded`.
- ✅ **8.** Phone calls through Communication Services, consent-gated and off by default.
- ✅ **9.** Key Vault RS256 signing for manifests and packets; public key at `GET /api/signing-key`. Also fixed a real hole: a rewritten channel with a recomputed hash used to still verify.
- ✅ **10.** Foundry embeddings behind the semantic-fidelity check.
- ✅ **11.** Foundry escalation classifier that can only add a human handoff, never remove one.
- ✅ **12.** Azure AI Search over the verified agency pages, exact quotes only.
- ✅ **13.** Application Insights, capped at 0.1 GB/day.
- ✅ **14.** Azure Maps geocoding on the server, Census as fallback.

## Together (after 2 and 3)

- ⬜ **15. First run with real keys.** Fix provider bugs, then measure how often each language gets withheld (es, ar, prs, tl). This is the one that turns "code exists" into "it works".
- ⬜ **16. Publish the code to the Function App**, via Deployment Center → GitHub. **Needs your OK to push to `iamenibrahim/rubicon`** — and if that repo is public, say so, because one file carries your email address.
- ⬜ **17. Connect the Copilot Studio agent:** upload `copilot/last-mile-handoff.swagger.json` as a REST tool, paste the instructions from `copilot/README.md`, publish to Teams.
- ⬜ **18. Run Foundry Evaluations** on the corruption-test set; screenshot the dashboard for the deck.
- ⬜ **19. Compute the impact number** from ACS B16004 and the alert archive.

## Thursday night (freeze)

- ⬜ **20. Update the deck:** one slide per Microsoft service and its job, the real-data numbers, the Copilot agent, and the honest limits below.
- ⬜ **21. Record the offline fallback video** with `LAST_MILE_OFFLINE=1`.
- ⬜ **22. Freeze.**

## Say these out loud in the pitch, unprompted

- **Region.** This runs in Canada Central because Azure refuses US regions on a student subscription. An agency deployment uses `eastus`, Azure's Virginia region, to keep residents' data in state — a parameter, not a code change. **Do not claim Virginia data residency.**
- **Cosmos DB is not deployed.** Free-tier Cosmos would not provision in Canada Central. The app uses its SQLite store, the same one every local run uses.
- **Not everything is free tier.** Translator, Speech and Content Safety are pay-per-character because soft-deleted accounts hold the one-free-account slot. Demo volume is a fraction of a cent.
- **Trust anchor.** NWS alerts are not individually signed. We attest to a payload fetched over TLS plus our own signature — not an NWS signature.
- **The corruption numbers** come from five *mechanical* corruption classes. Say "mechanical" every time.

## If time runs short

Cut in this order: **18** (Foundry Evaluations), **19** (impact number), **17** (Copilot agent).

Never cut: **2, 3, 15** — without them no Azure service is proven to work.

## Microsoft services scorecard

| Service | Role | Status |
|---|---|---|
| Azure Functions | API host + NWS ingest timer | **Deployed**; code not published yet (item 16) |
| Foundry (gpt-4.1-mini) | Plain-language rewrite, entailment judge, escalation classifier | Resource deployed; **no model yet** (item 2) |
| Foundry embeddings | Semantic-fidelity check (cosine, multilingual) | Resource deployed; **no model yet** (item 2) |
| Azure AI Translator | Translation + round-trip check | **Deployed** (S1); never called yet |
| Azure AI Speech | Spoken output of verified text | **Deployed** (S0); never called yet |
| Azure AI Content Safety | Output guard before rendering | **Deployed** (S0); never called yet |
| Azure AI Search | Exact-quote retrieval; Copilot tool | **Deployed** (free tier); index builds on first query |
| Azure Maps | Map + server-side geocoding | **Deployed** |
| Key Vault | Manifest + packet signing (RS256), public key at `/api/signing-key` | **Deployed** with the RSA key |
| Application Insights | Request latency and failures; 0.1 GB/day cap | **Deployed** |
| Communication Services | SMS + phone calls, consent-gated | **Deployed**; needs a trial number to actually send |
| Cosmos DB | Alerts, manifests, render cache | **Not deployed** — see above |
| Foundry Evaluations | Corruption-test dashboard | ⬜ (item 18) |
| Copilot Studio | Caseworker agent in Teams | Pieces ready; ⬜ connect (item 17) |
