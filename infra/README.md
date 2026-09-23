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

