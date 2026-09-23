# Last-Mile Disaster Navigator

**Short description:** A privacy-first Virginia disaster-assistance navigator built around the **Last-Mile Protocol**: one authoritative, proof-carrying Disaster Action Packet is compiled into safe guidance for web, SMS, voice, and offline use. It asks only questions that can change the plan, preserves continuity with an anonymous recovery code, explains source-backed program matches, and escalates urgent or ambiguous cases to a prepared human handoff.

**Challenge:** Microsoft × CCI Innovation Challenge for Virginia — help people discover relevant disaster services by location, circumstances, and immediate need while reducing contact-center load and safely escalating sensitive, urgent, ambiguous, or high-impact cases.

> **Safety boundary:** This system never originates an alert and never decides benefit eligibility. Recommendations come from deterministic rules over reviewed source records. Microsoft Foundry explains those matches in plain language and evaluates transformations; it is not the eligibility engine.

## Central innovation: the Last-Mile Protocol

The app does not maintain four separate channel experiences. It creates one canonical Disaster Action Packet containing jurisdiction, disaster identifiers, applicability, needs, deadlines, actions, sources, safety constraints, escalation rules, and proof. A deterministic compiler derives the web, SMS, voice, and offline representations from that same packet. Microsoft Foundry may transform packet fields, but it cannot originate facts or alter locked dates and identifiers.

The checked-in recovery demo replays the official November 18, 2024 state for Tropical Storm Helene (`DR-4831-VA`) in Smyth County. It clearly states that the December 2, 2024 deadline has passed and must not be used as current application advice.

## What is implemented

- Need-first screening by city, ZIP, or optional address; urgent safety is always separated from benefit navigation.
- An information-gain intake engine: ZIP `24370` triggers a county question because the answer changes declaration applicability; irrelevant question groups are skipped.
- Canonical Disaster Action Packets and anonymous 24-hour `RBX-xxxxx` continuity codes containing only county, disaster ID, broad needs, constraints, and current step.
- Web, SMS, voice, and offline channel payloads compiled from the same packet with locked facts and a shared proof ID.
- Source-backed recommendations for shelter, food, FEMA Individual Assistance, SBA loans, disaster unemployment, document replacement, legal aid, emotional support, and Virginia 211.
- Confidence labels, eligibility caveats, document checklists, lost-document alternatives, official application links, and “why this fits” explanations.
- A one-time privacy receipt. The API does not persist citizen answers and never asks for SSNs, bank data, immigration status, or document uploads.
- A human handoff packet with a non-sensitive reference and summary for 211, 711, or emergency services.
- NWS CAP ingest with a real live endpoint and an explicitly labeled synthetic demo fallback.
- Geometry-derived inside / nearby / outside status. Language models do not decide geography.
- Entity locking for numbers, measurements, times, dates, roads, places, phones, URLs, and other critical spans.
- Four checks per alert segment: entity integrity, semantic fidelity, instruction coverage, and grounding. Failed segments show exact source English and an interpreter referral.
- HMAC-signed local manifests and a verification endpoint. Azure Key Vault is the production signing target.
- Azure AI Speech integration plus on-device speech fallback, PWA shell caching, print/save, text sizing, and responsive layout.
- A fraud red-flag check that never calls a message “safe.”
- A corruption-injection evaluation harness with honest, scoped reports.

The ten differentiating ideas are documented in [docs/innovations.md](docs/innovations.md); every one has a corresponding UI or API implementation.

## Run locally

Python 3.11+ is recommended.

```powershell
py -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m uvicorn api.main:app --reload
```

Open <http://127.0.0.1:8000>. No Azure credentials are required for the fallback demo.

Run the test and evaluation suites:

```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m eval.report
```

The report is written to `data/evaluation_report.json`. Do not quote its numbers without its scope: it evaluates the deterministic fallback against the checked-in demo fixture, not production model quality.

## Microsoft Foundry and Azure

The cloud path uses Microsoft services where each service has a specific job:

| Service | Load-bearing role |
|---|---|
| Microsoft Foundry Models | Plain-language transformation, grounded program explanations, strict entailment judge, evaluation dataset target |
| Azure AI Translator | Translation plus round-trip semantic check |
| Azure AI Speech | Neural spoken output of verified segments only |
| Azure AI Content Safety | Output guard before rendering in cloud mode |
| Azure Maps | Address geocoding and warning-polygon display; Census + local SVG are fallback paths |
| Azure Functions | Timer-triggered NWS ingest |
| Azure Cosmos DB | Alert, manifest, and safe render cache behind a store interface |
| Azure Key Vault | Production manifest signing key / asymmetric signing target |
| Azure Static Web Apps | No-build front end, linked to the API backend |
| Azure Functions | Consumption-based FastAPI backend, NWS ingest timer, and Event Grid SMS processing |
| Azure Communication Services | Consent-gated delivery of the already-verified SMS channel, plus Event Grid delivery reports and inbound recovery commands |

Copy `.env.example` to `.env`, supply only the services you have, and keep secrets in Key Vault in deployed environments. Every cloud call is isolated behind a provider and has a cached or deterministic fallback.

The Foundry provider calls the current OpenAI-compatible `/openai/v1/chat/completions` endpoint, uses JSON-only outputs, preserves sentinels structurally, and runs a separate entailment judgment. See [Microsoft Foundry’s REST reference](https://learn.microsoft.com/en-us/azure/foundry/openai/latest), [Azure AI Translator’s REST reference](https://learn.microsoft.com/en-us/rest/api/translator/translator/translate?view=rest-translator-v3.0), [Azure AI Content Safety](https://learn.microsoft.com/en-us/azure/ai-services/content-safety/quickstart-text), and [Azure AI Speech](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-text-to-speech).

### Student-credit deployment

`infra/student.bicep` is the cost-guarded hackathon deployment. It replaces the always-on App Service plan with a scale-to-zero Azure Functions Consumption plan capped at two instances, opts in to the Cosmos DB lifetime free tier at 400 RU/s, and uses F0 tiers for Translator, Speech, and Content Safety. It creates a Foundry resource but intentionally does not deploy a model; model availability must be checked first and inference is the main metered workload. Communication Services is created with SMS sending and automatic replies disabled, because an SMS-capable sender cannot be purchased with Azure trial credit.

Student subscriptions have a subscription-specific region allow-list. Check **Azure Policy > Assignments > Allowed resource deployment regions** and provide one of those values explicitly as the required `location` parameter. For this subscription Azure allows `canadacentral` and refuses `eastus`. An agency deployment would use `eastus`, Azure's Virginia region, to keep residents' data in state; that is a parameter change, not a code change. If free-tier Cosmos capacity is unavailable, deploy with `deployCosmos=false` and the app falls back to its local store.

The function host serves the complete FastAPI and web experience, so a separate paid web host is not required. The deployment also provisions Azure Maps and low-volume Storage. Do not add an always-ready Functions instance, dedicated App Service plan, VM, managed GPU deployment, or Cosmos throughput above 1,000 RU/s on the student subscription.

## API

| Route | Purpose |
|---|---|
| `POST /api/navigate` | Stateless service matching and handoff plan |
| `POST /api/intake/next` | Return only the next question that can change guidance |
| `POST /api/packet` | Build and sign a canonical Disaster Action Packet |
| `POST /api/packet/verify` | Verify packet signature, channel hash, and locked facts |
| `GET /api/continue/{code}` | Resume minimal anonymous state across channels |
| `POST /api/sms/send` | Send a verified packet through Azure Communication Services after explicit consent |
| `POST /api/sms/events` | Receive Event Grid validation, delivery reports, and privacy-preserving recovery commands |
| `GET /api/alerts` | Live Virginia NWS alerts with labeled fixture fallback |
| `POST /api/transform` | Lock, transform, verify, abstain, and manifest an alert |
| `POST /api/verify` | Validate manifest signature and rendered-content hash |
| `POST /api/speech` | Synthesize verified text with Azure AI Speech |
| `POST /api/fraud-check` | Check common red flags and official-domain allowlist |
| `GET /api/status` | Provider readiness without exposing secrets |
| `GET /api/evaluation` | Latest checked-in evaluation report |

Interactive OpenAPI documentation is at `/docs`.

### SMS pilot

The app compiles SMS text whether Azure is available or not. Real delivery is fail-closed and remains off until all of the following are configured: an Azure Communication Services endpoint or connection string, an approved SMS sender, `SMS_SEND_ENABLED=true`, and explicit consent in the request. For a student pilot, set `SMS_ALLOWED_TEST_RECIPIENTS` to a comma-separated list of your own E.164 test numbers. Automatic replies are a separate switch, `SMS_AUTOREPLY_ENABLED`, so an Event Grid subscription cannot begin sending replies accidentally.

The inbound command format is stateless with respect to the phone number: `CONTINUE RBX-xxxxx` returns the menu, and `RBX-xxxxx 1`, `2`, or `0` returns steps, document alternatives, or human help. This avoids keeping a phone-number-to-case mapping. Delivery reports retain only the provider message ID and status in the request lifecycle; phone numbers and message bodies are not logged by application code.

## Trust and scope disclosures

- NWS alerts from `api.weather.gov` are retrieved over TLS, but they are not individually signed in a way this app can verify end to end. A production manifest attests to the payload the service fetched and the transformation it performed. It is not an NWS signature.
- The checked-in Hampton Roads alert is synthetic test data using the NWS CAP/GeoJSON shape. It is always labeled **not an active warning**.
- The CAP `instruction` field is the only source of rendered emergency actions. If it is empty, the UI says so and adds nothing.
- Program records are a reviewable snapshot, not a live guarantee that a disaster declaration or enrollment window is open. Users are sent to the authoritative agency to confirm and apply.
- Real IPAWS access requires a COG agreement and is an integration path, not a claimed implementation. C2PA is future work, not shipped provenance.
- The impact estimate intentionally remains unclaimed until a dated NWS archive and ACS B16004 run are supplied.

## Project deliverables

- [Architecture and threat boundaries](docs/architecture.md)
- [Ten implemented innovations](docs/innovations.md)
- [Evaluation method and honest results](docs/evaluation.md)
- [Demo and recording script](docs/demo-script.md)
- `deliverables/Last-Mile-Navigator-Pitch.pptx` (generated and visually verified in this repository)
- [Security policy](SECURITY.md)

## Repository layout

```text
api/          FastAPI app, safety mechanisms, providers, navigation rules
data/         Reviewed program records, demo CAP fixture, evaluation report
eval/         Corruption injection, metrics, impact-analysis guard
functions/    Azure Functions timer ingest entry point
infra/        Azure deployment templates and service map
tests/        Mechanism-level and full-flow tests
web/          No-build, responsive PWA
docs/         Architecture, evaluation, innovation, and demo artifacts
deliverables/ Hackathon presentation
```

## Submission copy

> Last-Mile gives a disaster survivor a source-backed plan without making them learn the government org chart. A person shares only a city or ZIP, today’s needs, and optional broad context. Deterministic rules identify programs; Microsoft Foundry turns reviewed source text into clear explanations and evaluates emergency-language transformations. Every recommendation shows why it may fit, what to gather, where to apply, and when a person should take over. Critical alert facts are locked before AI, checked four ways, and refused segment-by-segment when uncertain. The experience works with cached data, speech, print, and offline shell support—and it is candid about what it cannot verify.
