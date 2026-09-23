# TODO: Microsoft × CCI Innovation Challenge

Today: Wed Sep 23. **Feature freeze: end of Thu Sep 24.** Fri Sep 25 is pitch only, with no new code.

Goal: the most Microsoft-native version of the project, with every service doing real work.

Legend: ✅ done · ⏳ in progress · ⬜ not started

## You (Azure portal)

- ⏳ **1. Deploy the Azure resources.** Deploy a custom template → load `infra/student.json` → subscription **Azure for Students** (not `its-avd-001`) → resource group `last-mile-student-rg` → **Location `canadacentral`** → Foundry Model Deployment `last-mile` → Create.
- ⬜ **2. Deploy the models in Foundry.** Open the `…foundry` resource → Go to Foundry portal → Deployments:
  - `gpt-4.1-mini`, deployment name exactly **`last-mile`**
  - `text-embedding-3-small`
- ⬜ **3. Hand over the keys.** Create `azure-settings.txt` in this folder containing:
  - the Function App (`…api`) → Settings → Environment variables → Advanced edit (copy everything)
  - the Foundry resource → Keys and Endpoint → Key 1

  Never paste keys in chat. `python scripts/settings_to_env.py` turns it into `.env` (both files are gitignored). The app now loads `.env` on start.
- ⬜ **4. Check Copilot Studio access** at <https://copilotstudio.microsoft.com> with your GMU account.
- ⬜ **5. Get a free Census API key** at <https://api.census.gov/data/key_signup.html>.

## Claude (code, no keys needed)

- ✅ **6. Copilot Studio caseworker agent pieces:** the `GET /api/handoff/{code}` endpoint, a test for it, `copilot/last-mile-handoff.swagger.json`, and `copilot/README.md`.
- ✅ **7. Move the evidence over from `hackily`** (now the `grounded` package, served at `/grounded`; 116 tests under `tests/grounded`):
  - the 80 real NWS alerts replace the single synthetic alert in the evaluation
  - hash-checked FEMA, eCFR, SBA and SAMHSA quotes
  - the OpenFEMA deadline rules, including the 60-day late window (44 CFR 206.112(d))
  - rerun the evaluation afterward
- ✅ **8. Finish and commit the phone-call feature** (Communication Services Call Automation), off by default.
- ✅ **9. Key Vault signing** for the provenance manifests and packets, using an asymmetric key so anyone can check a signature with the public key. `GET /api/signing-key` publishes it. The template now creates the vault and key. **If you already deployed, redeploy `infra/student.json` to the same resource group to add it.**
- ✅ **10. Foundry embeddings** behind the semantic-fidelity check (does the translation still mean the same thing).
- ✅ **11. Foundry escalation classifier** that can only add a "hand to a person" escalation, never remove one.
- ✅ **12. Azure AI Search** over the FEMA, eCFR, SBA and SAMHSA source documents, returning exact quotes only (`/grounded/api/quotes/search`; also the Copilot agent's second tool). Free tier in the template.
- ✅ **13. Application Insights** on the free tier, logging no personal data, for live latency figures.
- ✅ **14. Azure Maps geocoding on the server**, falling back to the Census geocoder.

## Together (after 1–3)

- ⬜ **15. First run with real keys:** fix provider bugs, and measure how often each language gets withheld (es, ar, prs, tl).
- ⬜ **16. Put the code on Azure** through the Function App → Deployment Center → GitHub. No command line needed.
- ⬜ **17. Connect the Copilot Studio agent:** put the Function App's host name into the swagger file, upload it as a REST API tool, and publish to Teams.
- ⬜ **18. Run Foundry Evaluations** on the corruption-test set and screenshot the dashboard for the deck.
- ⬜ **19. Compute the impact number** from ACS table B16004 and the alert archive.

## Thursday night (freeze)

- ⬜ **20. Update the deck:** a slide listing each Microsoft service and its job, the real-data numbers, and the Copilot agent.
- ⬜ **21. Record the offline fallback video** with every cloud call forced to its local fallback.
- ⬜ **22. Freeze.**

## If time runs short

Cut in this order: **12** (AI Search), **13** (App Insights), **8** (phone calls).

These make the demo real, so never cut them: **1–3, 7, 15–17**.

## Microsoft services scorecard

| Service | Role | Status |
|---|---|---|
| Foundry (gpt-4.1-mini) | Plain-language rewrite, entailment judge, escalation classifier | Code exists, never run with keys |
| Foundry embeddings | Semantic-fidelity check (cosine, multilingual) | Code done; runs once the embedding model is deployed |
| Foundry Evaluations | Corruption-test dashboard | ⬜ (item 18) |
| Azure AI Translator | Translation + round-trip check | Code exists, never run with keys |
| Azure AI Speech | Spoken output of verified text | Code exists, never run with keys |
| Azure AI Content Safety | Output guard before rendering | Code exists, never run with keys |
| Azure AI Search | Exact-quote retrieval over sources; Copilot tool | Code + template done; runs once deployed |
| Azure Maps | Map + server-side geocoding | Code done; runs once the key is set |
| Azure Functions | API host + NWS ingest timer | Template ready, deploying (item 1) |
| Cosmos DB | Alerts, manifests, render cache | Code exists, never run with keys |
| Key Vault | Manifest + packet signing (RS256), public key at `/api/signing-key` | Code + template done; runs once deployed |
| Communication Services | SMS + phone calls, consent-gated | Both built; need a trial number |
| Application Insights | Request latency and failures from the Functions host; 0.1 GB/day cap | In template; runs once deployed |
| Copilot Studio | Caseworker agent in Teams | Pieces ready; ⬜ connect (item 17) |
