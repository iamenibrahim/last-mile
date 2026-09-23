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

## Still to do

1. Deploy the Foundry models: `gpt-4.1-mini` named **`last-mile-gpt`**, and
   `text-embedding-3-small`. The template already points the app at those names.
2. Copy the Function App's app settings into `azure-settings.txt`, then run
   `python scripts/settings_to_env.py` for a local `.env`.
3. Publish the code to the Function App (Deployment Center -> GitHub).
4. Point `copilot/last-mile-handoff.swagger.json` at
   `lmva3fcshw5lauukqapi.azurewebsites.net` and upload it in Copilot Studio.
