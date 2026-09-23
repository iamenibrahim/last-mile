# Azure deployment notes

`main.bicep` provisions the hosting and service resources, but it intentionally does not guess a Foundry model deployment because model and region availability and agency approval vary. After deployment:

1. Deploy an approved chat model in the provisioned Microsoft Foundry resource and set `AZURE_FOUNDRY_MODEL`.
2. Assign the App Service managed identity the minimum Foundry and Cosmos data-plane roles.
3. Put Translator, Speech, Content Safety, Azure Maps, and signing material in Key Vault; expose them as App Service Key Vault references.
4. Replace the placeholder `apiContainerImage` with the built project image.
5. Link the Static Web App to the App Service API or configure its API route.
6. Restrict CORS, networking, and public access for the agency environment.
7. Use an asymmetric Key Vault key and include its version in production manifests; local HMAC is for demos only.

The template favors a legible hackathon deployment over a claim of production hardening. Private endpoints, WAF, multi-region failover, and agency identity policy remain deployment decisions.

## Student subscription

Use `student.bicep` for the $100 Azure for Students credit. It compiles the FastAPI application into an Azure Functions HTTP catch-all and provisions only free or consumption-based services. Application Insights is included on a Log Analytics workspace with a hard 0.1 GB/day ingestion cap, inside the free monthly allowance. The template deliberately excludes an always-on App Service plan, model deployments, phone numbers, and managed compute. Deploy the Foundry model separately only after confirming model availability and quota in the selected region.

Azure for Students applies a subscription-specific allowed-region policy. In the portal, open **Policy > Assignments > Allowed resource deployment regions** and pass one listed region explicitly as the `location` parameter. Do not enter the literal expression `[resourceGroup().location]` in the custom-deployment form; Azure treats form values as strings and the policy rejects it.

The expected idle infrastructure cost is approximately zero, aside from negligible Function storage transactions. Cost is driven by actual Functions, Foundry, Maps, and any usage beyond the published free grants. Cosmos DB must retain `enableFreeTier: true`; that choice cannot be added after account creation.
