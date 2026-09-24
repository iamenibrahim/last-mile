# Authoritative sources and Microsoft reference map

This map separates evidence the application actually uses from design references and future integration options. A link in this document is not, by itself, an implementation claim.

## Government sources

| Source | Project role | Status |
|---|---|---|
| [DisasterAssistance.gov](https://www.disasterassistance.gov/) | Official FEMA application and application-status destination shown to citizens | Used in the reviewed program catalog and UI |
| [OpenFEMA Data Sets](https://www.fema.gov/about/openfema/data-sets) | Dataset discovery and field definitions for declarations, assistance, and archived alerts | Used for dataset selection and provenance |
| [OpenFEMA API Documentation](https://www.fema.gov/about/openfema/api) | Keyless machine-readable declaration, housing-assistance, and IPAWS archive access | Implemented in `grounded/fema.py`; cached snapshots preserve demo reliability |
| [OpenFEMA Sample Projects](https://github.com/FEMA/openfema-samples) | FEMA-published examples for API access and analysis patterns | Engineering reference only; no sample code is represented as Last-Mile code |
| [FEMA Disaster Fraud Guidance](https://www.fema.gov/assistance/individual/disaster-fraud) | Reviewed warnings about fees, impersonation, identity theft, and suspicious payment requests | Used by the fraud shield and evidence corpus; the app flags risk and never declares a message safe |
| [FEMA Disaster Recovery Center Locator](https://egateway.fema.gov/ESF6/DRCLocator) | Official route to nearby in-person application, case-status, letter, housing, and referral help | Linked from the assistance experience; center availability remains FEMA-controlled |

FEMA and DisasterAssistance.gov pages sometimes reject automated retrieval. The evidence corpus therefore stores dated, hash-checked review snapshots and sends the citizen to the live official site for current action. OpenFEMA API responses are separately cached with retrieval metadata. Last-Mile never treats its cache as proof that an application window or recovery center is currently open.

## Microsoft technology and design references

| Reference | Project role | Status |
|---|---|---|
| [Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/) | Plain-language transformation, grounded explanation, and entailment judgment over supplied evidence | Implemented and exercised live with a Phi model |
| [Azure Translator](https://learn.microsoft.com/en-us/azure/ai-services/translator/) | Spanish, Arabic, Dari, and Filipino translation plus round-trip verification | Implemented and exercised live |
| [Voice Live API](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/voice-live) | Potential low-latency speech-to-speech contact-center channel with interruption handling and function calling | Future option; the submission currently uses Azure AI Speech text-to-speech and has prepared ACS Call Automation |
| [Microsoft Inclusive Design](https://inclusive.microsoft.design/) | Design reference for multiple channels, text sizing, keyboard access, plain language, speech, and human alternatives | Applied as a design lens; not a claim of formal certification or user validation |
| [Microsoft Accessibility](https://www.microsoft.com/en-us/trust-center/compliance/accessibility) | Accessibility governance and procurement reference for a production agency deployment | Reference only; formal WCAG/Section 508 review remains required |
| [Microsoft Responsible AI Tools and Practices](https://www.microsoft.com/en-us/ai/tools-practices) | Human oversight, transparency, evaluation, monitoring, and fail-closed design reference | Reflected in source citations, deterministic eligibility boundaries, abstention, telemetry, and human escalation |
| [Microsoft Fabric](https://learn.microsoft.com/en-us/fabric/) | Potential partner-scale analytics for anonymous operational and contact-center outcome data | Not implemented; intentionally excluded from the student deployment to avoid cost and an unsupported submission claim |

## Claim discipline

- **Implemented** means code exists and the live Azure provider was exercised.
- **Prepared** means the code/configuration surface exists but a required external sender, tenant publication, or account entitlement is missing.
- **Reference** means the material influenced design or governance only.
- **Future option** means it is architecturally relevant but absent from the submitted runtime.

The production evidence for implemented services is recorded in `grounded_eval/results/LIVE_OPERATIONAL_EVIDENCE.md`. Human accessibility and native-language validation remain separate work items; Microsoft reference material is not a substitute for testing with people.
