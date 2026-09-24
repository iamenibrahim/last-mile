# Deployed environment

Deployed 2026-09-23 from `infra/student.json` into the Azure for Students
subscription `9845da8a-0783-4120-8a24-daaddf53312e`.

| | |
|---|---|
| Resource group | `last-mile-student-rg` |
| Region | `canadacentral` |
| Name prefix | `lmva` |
| Function App | `lmva3fcshw5lauukqapi` |
| Application URL | <https://lmva3fcshw5lauukqapi.azurewebsites.net> |
| Foundry resource | `lmva3fcshw5lauukqfoundry` |
| Foundry endpoint | <https://lmva3fcshw5lauukqfoundry.openai.azure.com> |
| Key Vault | <https://kvlmva3fcshw5lauukq.vault.azure.net/> (key `manifest-signing`, RS256) |
| Communication Services | `lmva3fcshw5lauukqcommunication` |
| Cosmos DB | **not deployed** (`deployCosmos=false`) |

## What differs from the template's defaults, and why

**Name prefix `lmva`, not `lastmile`.** An earlier attempt created and then
deleted the `lastmile...` Cognitive Services accounts. Azure soft-deletes those
and holds the names for 48 hours, so recreating them failed with
`FlagMustBeSetForRestore`. A new prefix gives new names.

**Translator S1, Speech S0, Content Safety S0 - not F0.** A subscription gets
one free account per Cognitive Services kind, and the soft-deleted accounts
still hold those slots (`CanNotCreateMultipleFreeAccounts`). All three are
pay-per-character; demo volume costs a fraction of a cent. Foundry was always
S0 and is billed per token.

**Cosmos DB skipped.** Free-tier Cosmos would not provision in `canadacentral`
(`ResourceDeploymentFailure`, terminal state `Failed`) on two attempts. With
`deployCosmos=false` the app's `AZURE_COSMOS_ENDPOINT` is empty and
`api/store.py` uses its SQLite store, which is what every local run already
uses. A failed account named `lmva3fcshw5lauukqcosmos` may still be in the
resource group; it holds no data and can be deleted.

**Region `canadacentral`.** Azure refuses `eastus` on this student
subscription (`RequestDisallowedByAzure`). An agency deployment would use
`eastus`, Azure's Virginia region, to keep residents' data in state - a
parameter change, not a code change. Do not claim Virginia data residency for
this demo.

## Foundry models

**This subscription has zero Azure OpenAI quota.** The Foundry quota page reads
`0/0` for every OpenAI model, in every region, for every deployment type. That
is a standing Azure for Students limit, not something the template controls, so
`gpt-4.1-mini` and `text-embedding-3-small` cannot be deployed at all. The same
is true of the Cohere "Direct from Azure" models.

What does deploy is Microsoft's own first-party models, which have quota
(20,000 TPM). Deployed 2026-09-23:

| Deployment | Model | Type |
|---|---|---|
| `last-mile-gpt` | **Phi-4-mini-instruct** (Microsoft, 3.8B, chat completion) | Global Standard |

Verified in the playground: *"Residents in low-lying areas should evacuate
immediately to higher ground."* returns *"People living in places that are close
to the water should leave right away and go to a safer, higher place."* That is
the simplification the pipeline needs, and Phi is multilingual (Spanish, Arabic
and others).

**No embedding model is deployed**, because none can be. The semantic-fidelity
check therefore keeps its honest fallback, which reports the method as "provider
confidence (no embeddings configured; not a meaning check)". Meaning is still
checked by the Foundry entailment judge, which now runs on Phi.
`AZURE_FOUNDRY_EMBED_MODEL` was removed from both the Function App and local
`.env` on 2026-09-23, so the fallback is explicit rather than exception-driven.

For the pitch: say that model choice is a deployment parameter. An agency
subscription with OpenAI quota changes one setting; nothing in the code changes.

## Deployment and live verification

Published from `iamenibrahim/rubicon` branch `main` by
`.github/workflows/deploy-function-app.yml`. The publish profile is stored only
as a GitHub Actions secret. Commit `2b170f0` is live.

Verified against the deployed Function App on 2026-09-23:

- `/healthz`, `/api/status`, `/api/signing-key`, `/api/packet`,
  `/api/packet/verify`, `/api/transform`, `/grounded/`, and
  `/grounded/api/quotes/search` return their application contracts.
- Foundry/Phi rewriting and entailment judging executed; Azure Translator,
  Speech, Content Safety, Maps, AI Search, and Key Vault RS256 all executed.
- Azure AI Search returned five exact, hash-located quotes with zero dropped
  results. Azure Maps returned an address-level match.
- Application Insights received live Function traces; its connection string
  matches the deployed resource.
- Gitignored `azure-settings.txt` and `.env` were generated from the Function
  App settings.
- The cost-bounded four-language run is recorded in
  `grounded_eval/results/LIVE_MULTILINGUAL_AZURE.md`.

Still external/manual: upload the Copilot swagger into Copilot Studio, update
the pitch deck, record the fallback demo, and freeze.
