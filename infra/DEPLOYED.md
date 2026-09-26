# Deployed environment

Latest live measurements and verification evidence are recorded in
[`LIVE_OPERATIONAL_EVIDENCE.md`](../grounded_eval/results/LIVE_OPERATIONAL_EVIDENCE.md).
The current repository is `iamenibrahim/last-mile`; its `e12364a` deployment
and security workflows succeeded. Historical provisioning details follow.

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
`deployCosmos=false` the app's `AZURE_COSMOS_ENDPOINT` is empty. Anonymous
recovery-code continuity uses Azure Table Storage in the deployed environment;
the local development/render store may use SQLite. A failed account named `lmva3fcshw5lauukqcosmos` may still be in the
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

**No embedding model is deployed**, because none can be. For a translation the
semantic-fidelity check therefore keeps its honest fallback, which reports the
method as "provider confidence (no embeddings configured; not a meaning check)",
with the Translator round-trip covering the cases where a back-translation
exists. For English the check is no longer a fallback at all: it is Foundry
reverse entailment, asking whether the simplified output still carries every
claim the source made. Meaning is also checked in the forward direction by the
Foundry entailment judge, which runs on Phi.
`AZURE_FOUNDRY_EMBED_MODEL` was removed from both the Function App and local
`.env` on 2026-09-23, so the fallback is explicit rather than exception-driven.

For the pitch: say that model choice is a deployment parameter. An agency
subscription with OpenAI quota changes one setting; nothing in the code changes.

## Deployment and live verification

Published from `iamenibrahim/last-mile` branch `main` by
`.github/workflows/deploy-function-app.yml`. The publish profile is stored only
as a GitHub Actions secret. The successful deployment workflow for `e12364a` is
[run 36204455943](https://github.com/iamenibrahim/last-mile/actions/runs/36204455943).
This is workflow evidence, not a runtime commit attestation.

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

## Communication Services: what the portal actually allows (2026-09-24)

Checked in the portal, not inferred. The resource holds one number:

| Number | Operator | Status | Cost | Type |
|---|---|---|---|---|
| +1 844-919-7508 | Microsoft | **Free Trial** | Free | Toll-free, US |

Two portal blades refuse it, and it is important not to over-read them:

- **Try SMS** - the "Send message from" list is empty and disabled, and Send is
  greyed out. A trial number carries no SMS capability, so the app cannot text
  a resident from this resource. Outbound SMS needs a **purchased** number.
- **Try Phone Calling** - refuses in red: *"This resource is not configured to
  make an outbound call. Please purchase a phone number or configure Direct
  Routing first."*

**The Try Phone Calling refusal is about that blade, not about calling.** A
trial number can place outbound PSTN calls through Call Automation once the
recipient is verified, which is the path this app actually uses. Verification
lives on the number itself, not in that blade:

> Phone numbers -> select the number -> **Trial details** tab ->
> **Manage verified phone numbers** -> Add -> enter the number and country
> code -> choose SMS or automated voicemail -> Next -> enter the one-time
> passcode.

Trial limits: up to **three** verified recipients, 60 inbound and 60 outbound
minutes, 5 minutes maximum per call, US billing addresses only, no emergency
numbers. More than three recipients requires a purchased number.

**Updated voice status:** a verified test recipient received a call and heard
audio on September 24. The September 25 status
check still reports voice enabled. A repeat handset/DTMF walkthrough remains
human evidence to collect. **SMS still needs a purchased, approved sender.**

The portal also now shows a retirement notice on this resource: "Azure
Communication Services capabilities in this resource are being retired or will
change" - <https://aka.ms/acs-retirement>. Read it before committing to an ACS
delivery path in any agency deployment.

**Say this plainly in the pitch.** SMS and voice are implemented, consent-gated
and covered by tests, and they have never delivered to a real handset. The
reason is a subscription limit, not an unfinished integration - the same code
sends the moment a purchased number exists.
