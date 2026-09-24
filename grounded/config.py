"""Central configuration. Every Azure surface is optional by construction.

INVARIANT (brief section 5): the demo must run with zero Azure credentials.
Setting an env var upgrades a provider from its local implementation to the
Azure one; unsetting it (or an Azure call failing) degrades back down and the
degradation is recorded in the manifest rather than hidden.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data" / "grounded"
CACHED_ALERTS_DIR = DATA_DIR / "cached_alerts"
FIXTURES_DIR = DATA_DIR / "fixtures"
GAZETTEER_PATH = DATA_DIR / "gazetteer_va.json"
WEB_DIR = REPO_ROOT / "web" / "grounded"
# Writable runtime state. Azure Functions runs from a read-only package, so the
# cache and dev key go to the temp dir there.
STATE_DIR = (
    Path(tempfile.gettempdir()) / "last-mile-grounded"
    if os.environ.get("APP_ENV") == "azure"
    else DATA_DIR
)

# NWS requires a descriptive User-Agent with contact info (brief section 4).
NWS_USER_AGENT = os.environ.get(
    "NWS_USER_AGENT",
    "last-mile-alert/1.0 (CCI Innovation Challenge prototype; https://github.com/iamenibrahim/rubicon)",
)
NWS_BASE = "https://api.weather.gov"
CENSUS_GEOCODER = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
CENSUS_API = "https://api.census.gov/data"

# Demo languages. NON-GOAL section 11: no more than 4 target languages.
SUPPORTED_LANGUAGES: dict[str, dict[str, str]] = {
    "es": {"name": "Spanish", "endonym": "Espanol", "dir": "ltr", "voice": "es-US-PalomaNeural"},
    "prs": {"name": "Dari", "endonym": "Dari", "dir": "rtl", "voice": "fa-IR-DilaraNeural"},
    "ar": {"name": "Arabic", "endonym": "Arabiyya", "dir": "rtl", "voice": "ar-EG-SalmaNeural"},
    "tl": {"name": "Tagalog", "endonym": "Tagalog", "dir": "ltr", "voice": "fil-PH-BlessicaNeural"},
}

TARGET_READING_GRADE = float(os.environ.get("TARGET_READING_GRADE", "7.0"))

# Verification thresholds. Tuned on the dev corpus by eval/metrics.py; see
# eval/thresholds.json for the values the harness actually reports against.
SEMANTIC_FIDELITY_THRESHOLD = float(os.environ.get("SEMANTIC_FIDELITY_THRESHOLD", "0.82"))
INSTRUCTION_COVERAGE_THRESHOLD = float(os.environ.get("INSTRUCTION_COVERAGE_THRESHOLD", "0.99"))

# Distance band for "close to the edge" messaging.
NEAR_EDGE_KM = float(os.environ.get("NEAR_EDGE_KM", "5.0"))


@dataclass(frozen=True)
class AzureConfig:
    """Whether each Azure service is wired. Absent key => local provider.

    Foundry and Key Vault also accept the names the Rubicon app and the
    student Bicep template use, so one .env configures both pipelines.
    """

    translator_key: str | None = field(default_factory=lambda: os.environ.get("AZURE_TRANSLATOR_KEY"))
    translator_region: str | None = field(default_factory=lambda: os.environ.get("AZURE_TRANSLATOR_REGION"))
    translator_endpoint: str = field(
        default_factory=lambda: os.environ.get(
            "AZURE_TRANSLATOR_ENDPOINT", "https://api.cognitive.microsofttranslator.com"
        )
    )
    speech_key: str | None = field(default_factory=lambda: os.environ.get("AZURE_SPEECH_KEY"))
    speech_region: str | None = field(default_factory=lambda: os.environ.get("AZURE_SPEECH_REGION"))
    openai_key: str | None = field(default_factory=lambda: os.environ.get("AZURE_OPENAI_KEY") or os.environ.get("AZURE_FOUNDRY_API_KEY"))
    openai_endpoint: str | None = field(default_factory=lambda: os.environ.get("AZURE_OPENAI_ENDPOINT") or os.environ.get("AZURE_FOUNDRY_ENDPOINT"))
    openai_chat_deployment: str | None = field(
        default_factory=lambda: os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT") or os.environ.get("AZURE_FOUNDRY_MODEL")
    )
    openai_embed_deployment: str | None = field(
        default_factory=lambda: os.environ.get("AZURE_OPENAI_EMBED_DEPLOYMENT") or os.environ.get("AZURE_FOUNDRY_EMBED_MODEL")
    )
    openai_api_version: str = field(
        default_factory=lambda: os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")
    )
    content_safety_key: str | None = field(default_factory=lambda: os.environ.get("AZURE_CONTENT_SAFETY_KEY"))
    content_safety_endpoint: str | None = field(
        default_factory=lambda: os.environ.get("AZURE_CONTENT_SAFETY_ENDPOINT")
    )
    maps_key: str | None = field(default_factory=lambda: os.environ.get("AZURE_MAPS_KEY"))
    keyvault_url: str | None = field(default_factory=lambda: os.environ.get("AZURE_KEYVAULT_URL") or os.environ.get("AZURE_KEY_VAULT_URL"))
    keyvault_key_name: str | None = field(default_factory=lambda: os.environ.get("AZURE_KEYVAULT_KEY_NAME"))
    cosmos_url: str | None = field(default_factory=lambda: os.environ.get("AZURE_COSMOS_URL"))
    cosmos_key: str | None = field(default_factory=lambda: os.environ.get("AZURE_COSMOS_KEY"))


AZURE = AzureConfig()

# Offline mode forces every provider to its local implementation, even if keys
# are present. Used by the test suite and by the Day-4 fallback demo.
OFFLINE = os.environ.get("LAST_MILE_OFFLINE", "0") == "1"

# Local HMAC signing key for the manifest when Key Vault is not configured.
# Dev-only: a real deployment signs with an asymmetric Key Vault key so that
# verification does not require the signing secret.
LOCAL_SIGNING_KEY_PATH = STATE_DIR / ".dev_signing_key"
