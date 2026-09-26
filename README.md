# Last-Mile Disaster Navigator

Last-Mile helps people find disaster assistance without making them navigate a maze of agencies. A user shares a ZIP code, their immediate needs, and a small amount of optional context. The app returns a short action plan with relevant programs, documents to gather, official application links, and a clear path to human help.

**Live demo:** [lmva3fcshw5lauukqapi.azurewebsites.net/grounded](https://lmva3fcshw5lauukqapi.azurewebsites.net/grounded/)

This project was built for the Microsoft × CCI Innovation Challenge for Virginia.

> Last-Mile does not create emergency alerts or decide whether someone qualifies for benefits. It matches reviewed source records with deterministic rules. AI is used to explain and translate those results, and the app withholds a transformation when it cannot verify it.

## Try the demo

Use ZIP code `24370` and choose Smyth County. The demo replays the official October 21, 2024 state for Tropical Storm Helene (`DR-4831-VA`). At that point, the December 2 deadline was 42 days away. This is a historical replay for demonstration, not current application advice.

The main flow shows:

- county disambiguation when a ZIP crosses county lines;
- a short, need-based action plan;
- source evidence for each recommendation;
- documents to gather and official places to apply;
- anonymous recovery codes for continuing later;
- human-help options for urgent or uncertain situations;
- web, SMS, voice, print, and offline versions of the same plan.

## How it works

Last-Mile builds one **Disaster Action Packet** from the user's answers and reviewed program data. That packet contains the facts, recommendations, deadlines, sources, safety limits, and proof needed to produce each channel.

```text
User answers
    ↓
Need-first intake and deterministic matching
    ↓
Reviewed government and nonprofit sources
    ↓
Signed Disaster Action Packet
    ↓
Web · SMS · Voice · Print · Offline
```

This keeps the guidance consistent across channels. Microsoft Foundry can turn reviewed material into plain language, but it cannot invent programs, change dates, or make eligibility decisions. Critical details such as phone numbers, URLs, locations, measurements, and identifiers are locked before transformation and checked afterward.

If a source is stale, two official sources conflict, or a generated explanation fails verification, the app stops and shows the reviewed source text or a human-help route.

## Privacy and safety

- No Social Security numbers, bank information, immigration status, or document uploads.
- Citizen answers are not stored by the API.
- Recovery codes contain only broad, non-sensitive state and expire after 24 hours.
- Urgent safety needs are separated from benefit navigation.
- Recommendations include citations, caveats, and visible review dates.
- Saved offline packets can be cryptographically verified.
- The synthetic alert fixture is always labeled as test data.

## Run locally

Python 3.11 or newer is recommended.

```powershell
py -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m uvicorn api.main:app --reload
```

Open [http://127.0.0.1:8000/grounded/](http://127.0.0.1:8000/grounded/). The demo works without Azure credentials by using checked-in reviewed data and deterministic fallbacks.

Run the tests with:

```powershell
.\.venv\Scripts\python -m pytest -q
```

## Azure services

The deployed version uses Azure Functions for the FastAPI app and scheduled NWS ingest. Azure Table Storage keeps short-lived recovery codes available across instances. Microsoft Foundry, Translator, Speech, Content Safety, Maps, AI Search, Key Vault, and Communication Services each sit behind a provider boundary with a safe fallback or fail-closed behavior.

Copy `.env.example` to `.env` to configure only the services you want to use. Do not commit secrets. The student deployment template is in `infra/student.bicep` and is designed for a small, scale-to-zero Azure deployment.

Interactive API documentation is available at `/docs`. The most useful routes are:

| Route | Purpose |
|---|---|
| `POST /api/navigate` | Match needs to reviewed assistance programs |
| `POST /api/intake/next` | Ask the next question that could change the plan |
| `POST /api/packet` | Build and sign a Disaster Action Packet |
| `POST /api/packet/verify` | Verify the packet and its locked facts |
| `GET /api/continue/{code}` | Resume an anonymous session |
| `GET /api/alerts` | Read current Virginia NWS alerts with a labeled demo fallback |
| `POST /api/transform` | Transform and verify alert text |
| `GET /api/status` | Check provider readiness without exposing secrets |

## Repository guide

```text
api/          FastAPI application and provider integrations
grounded/     Packet, navigation, verification, and channel logic
data/         Reviewed program records and demo fixtures
functions/    Azure Functions entry point
infra/        Azure deployment templates and deployment notes
tests/        Unit, contract, safety, and full-flow tests
web/grounded/ Browser experience
docs/         Architecture, evaluation, and demo material
```

For a deeper technical review, see:

- [Architecture and trust boundaries](docs/architecture.md)
- [Authoritative sources](docs/authoritative-sources.md)
- [Evaluation method](docs/evaluation.md)
- [Implemented innovations](docs/innovations.md)
- [Live Azure evidence](grounded_eval/results/LIVE_OPERATIONAL_EVIDENCE.md)
- [Demo script](docs/demo-script.md)
- [Security policy](SECURITY.md)

Last-Mile's goal is simple: give someone a useful next step quickly, show where every important claim came from, and bring in a person when software should not make the call.
