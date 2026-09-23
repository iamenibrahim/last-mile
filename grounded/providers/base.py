"""Provider interfaces + the registry that picks Azure or local per service.

Brief section 5, INVARIANT - local-first fallback: every Azure call sits behind
an interface with a local stub. A throttled key or a bad deployment name must
not be able to kill the demo. When a provider degrades, `ProviderResult.engine`
records what actually ran, and that string lands in the manifest's transform
chain - so a fallback is visible in the artifact, not swallowed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol, Sequence

log = logging.getLogger("last_mile.providers")


@dataclass
class ProviderResult:
    """Return envelope carrying which engine really produced the value."""

    value: object
    engine: str
    degraded: bool = False
    detail: str | None = None


class Translator(Protocol):
    name: str

    def detect(self, text: str) -> str: ...

    def translate(self, texts: Sequence[str], target: str, source: str = "en") -> list[str]: ...


class Simplifier(Protocol):
    name: str

    def simplify(self, text: str, target_grade: float, lang: str = "en",
                 protect: frozenset[str] = frozenset()) -> str: ...

    @property
    def prompt_sha256(self) -> str: ...


class Embedder(Protocol):
    name: str
    # True when the vectors carry learned semantics; False for the local
    # lexical stub. The eval report must label which one produced a number.
    semantic: bool

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class Judge(Protocol):
    name: str
    # True for an LLM entailment judge, False for the local rule-based check.
    llm_backed: bool

    def entails(self, source: str, candidate: str) -> tuple[bool, float, str]: ...


class Speech(Protocol):
    name: str

    def synthesize(self, text: str, lang: str) -> tuple[bytes, str]:
        """Return (audio_bytes, mime_type)."""


class ContentSafety(Protocol):
    name: str

    def check(self, text: str) -> tuple[bool, list[str]]: ...


class Signer(Protocol):
    name: str
    key_id: str
    algorithm: str

    def sign(self, payload: bytes) -> str: ...

    def verify(self, payload: bytes, signature: str) -> bool: ...


@dataclass
class Registry:
    """Which implementation is live for each service, and why."""

    translator: Translator
    simplifier: Simplifier
    embedder: Embedder
    judge: Judge
    speech: Speech
    content_safety: ContentSafety
    signer: Signer
    notes: dict[str, str] = field(default_factory=dict)

    def describe(self) -> dict[str, str]:
        return {
            "translator": self.translator.name,
            "simplifier": self.simplifier.name,
            "embedder": self.embedder.name,
            "judge": self.judge.name,
            "speech": self.speech.name,
            "content_safety": self.content_safety.name,
            "signer": self.signer.name,
        }


_REGISTRY: Registry | None = None


def get_registry(force_local: bool = False) -> Registry:
    """Build (once) the live provider set.

    Each Azure provider is constructed only if its credentials are present and
    it can be imported; any failure falls back to the local implementation and
    is recorded in `notes`.
    """
    global _REGISTRY
    if _REGISTRY is not None and not force_local:
        return _REGISTRY

    from .. import config
    from . import local_providers as L

    notes: dict[str, str] = {}
    offline = force_local or config.OFFLINE

    translator: Translator = L.LocalTranslator()
    simplifier: Simplifier = L.LocalSimplifier()
    embedder: Embedder = L.LocalEmbedder()
    judge: Judge = L.LocalJudge()
    speech: Speech = L.LocalSpeech()
    safety: ContentSafety = L.LocalContentSafety()
    signer: Signer = L.LocalHmacSigner()

    if not offline:
        from . import azure_providers as A

        az = config.AZURE
        if az.translator_key:
            try:
                translator = A.AzureTranslator()
                notes["translator"] = "azure"
            except Exception as exc:  # pragma: no cover - credential path
                notes["translator"] = f"azure unavailable, local fallback: {exc}"
                log.warning("Azure Translator unavailable: %s", exc)
        else:
            notes["translator"] = "no AZURE_TRANSLATOR_KEY, local fallback"

        if az.openai_key and az.openai_endpoint:
            try:
                simplifier = A.AzureOpenAISimplifier()
                judge = A.AzureOpenAIJudge()
                notes["openai"] = "azure"
            except Exception as exc:  # pragma: no cover - credential path
                notes["openai"] = f"azure unavailable, local fallback: {exc}"
            if az.openai_embed_deployment:
                try:
                    embedder = A.AzureOpenAIEmbedder()
                except Exception as exc:  # pragma: no cover - credential path
                    notes["embedder"] = f"azure unavailable, local fallback: {exc}"
        else:
            notes["openai"] = "no AZURE_OPENAI_KEY, local fallback"

        if az.speech_key:
            try:
                speech = A.AzureSpeech()
                notes["speech"] = "azure"
            except Exception as exc:  # pragma: no cover - credential path
                notes["speech"] = f"azure unavailable, local fallback: {exc}"
        else:
            notes["speech"] = "no AZURE_SPEECH_KEY, local fallback"

        if az.content_safety_key and az.content_safety_endpoint:
            try:
                safety = A.AzureContentSafety()
                notes["content_safety"] = "azure"
            except Exception as exc:  # pragma: no cover - credential path
                notes["content_safety"] = f"azure unavailable, local fallback: {exc}"

        if az.keyvault_url and az.keyvault_key_name:
            try:
                signer = A.KeyVaultSigner()
                notes["signer"] = "azure key vault"
            except Exception as exc:  # pragma: no cover - credential path
                notes["signer"] = f"key vault unavailable, local HMAC fallback: {exc}"
        else:
            notes["signer"] = "no AZURE_KEYVAULT_URL, local HMAC dev key"
    else:
        notes["mode"] = "offline: all providers local by force"

    registry = Registry(
        translator=translator,
        simplifier=simplifier,
        embedder=embedder,
        judge=judge,
        speech=speech,
        content_safety=safety,
        signer=signer,
        notes=notes,
    )
    if not force_local:
        _REGISTRY = registry
    return registry


def reset_registry() -> None:
    """Test hook: drop the cached registry so env changes take effect."""
    global _REGISTRY
    _REGISTRY = None
