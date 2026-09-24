# TODO: Microsoft × CCI Innovation Challenge

Today: Wed Sep 23, evening. **Feature freeze: end of Thu Sep 24.** Fri Sep 25 is pitch only, with no new code.

Goal: the most Microsoft-native version of the project, with every service doing real work.

Deployed environment and its caveats: [infra/DEPLOYED.md](infra/DEPLOYED.md).

Legend: ✅ done · ⏳ in progress · ⬜ not started

## You (Azure portal / browser)

- ✅ **2. Foundry model deployed: `last-mile-gpt` = Phi-4-mini-instruct.** Verified working in the playground. **This subscription has zero Azure OpenAI quota** (`0/0` everywhere), so no OpenAI model could be used; Microsoft's own Phi has quota. No embedding model can be deployed either — see [infra/DEPLOYED.md](infra/DEPLOYED.md).

- ✅ **1. Deploy the Azure resources.** Done 2026-09-23 into `last-mile-student-rg`, `canadacentral`, prefix `lmva`.
- ✅ **3. Local Azure settings.** `azure-settings.txt` and `.env` were generated locally and remain gitignored. The nonexistent embedding deployment setting was removed.
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

- ✅ **15. First run with real keys.** Foundry, Translator, Speech, Content Safety, Maps, AI Search, Key Vault and Application Insights were exercised. Results for es/ar/prs/tl are checked in.
- ✅ **16. Publish the code to the Function App.** GitHub Actions continuously deploys `iamenibrahim/rubicon` `main` to `lmva3fcshw5lauukqapi`.
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
- **No OpenAI models.** Azure gives student subscriptions zero OpenAI quota, so the pipeline runs on **Microsoft's Phi-4-mini-instruct**. Model choice is a deployment parameter; an agency subscription changes one setting. This is a *better* Microsoft story, not an apology.
- **No embedding model**, for the same quota reason. The meaning check says so in its own output rather than pretending.
- **Not everything is free tier.** Translator, Speech and Content Safety are pay-per-character because soft-deleted accounts hold the one-free-account slot. Demo volume is a fraction of a cent.
- **Trust anchor.** NWS alerts are not individually signed. We attest to a payload fetched over TLS plus our own signature — not an NWS signature.
- **The corruption numbers** come from five *mechanical* corruption classes. Say "mechanical" every time.

## If time runs short

Cut in this order: **18** (Foundry Evaluations), **19** (impact number), **17** (Copilot agent).

Never cut: **2, 3, 15** — without them no Azure service is proven to work.

## Microsoft services scorecard

| Service | Role | Status |
|---|---|---|
| Azure Functions | API host + NWS ingest timer | **Live** with GitHub continuous deployment |
| Foundry (**Phi-4-mini-instruct**) | Plain-language rewrite, entailment judge, escalation classifier | **Deployed as `last-mile-gpt`**; verified in the playground |
| Foundry embeddings | Semantic-fidelity check (cosine, multilingual) | **Not possible** — no quota for any embedding model. Falls back, honestly labelled; the entailment judge still checks meaning |
| Azure AI Translator | Translation + round-trip check | **Live and exercised** (S1) |
| Azure AI Speech | Spoken output of verified text | **Live and exercised** (S0) |
| Azure AI Content Safety | Output guard before rendering | **Live and exercised** (S0) |
| Azure AI Search | Exact-quote retrieval; Copilot tool | **Live**; index populated and queried |
| Azure Maps | Map + server-side geocoding | **Live**; address-level result verified |
| Key Vault | Manifest + packet signing (RS256), public key at `/api/signing-key` | **Live**; packet verification uses the public key |
| Application Insights | Request latency and failures; 0.1 GB/day cap | **Live**; Function traces received |
| Communication Services | SMS + phone calls, consent-gated | **Deployed**; needs a trial number to actually send |
| Cosmos DB | Alerts, manifests, render cache | **Not deployed** — see above |
| Foundry Evaluations | Corruption-test dashboard | ⬜ (item 18) |
| Copilot Studio | Caseworker agent in Teams | Pieces ready; ⬜ connect (item 17) |
