"""Azure implementations, over plain REST so there is no SDK to install.

Every class here raises on construction if its credentials are missing, which
is what lets `base.get_registry()` fall back to the local implementation and
record the degradation. Nothing in this module is imported at startup unless a
key is present.

Brief section 6: each service is meant to be load-bearing, not decorative.
  Translator      - the actual translation
  Speech          - the audio that carries the point to a low-literacy reader
  OpenAI          - simplification, the entailment judge, and the embeddings
                    behind the semantic-fidelity check
  Content Safety  - the guard immediately before render
  Key Vault       - the manifest signing key
"""

from __future__ import annotations

import hashlib
import json
from typing import Sequence

import httpx

from .. import config

TIMEOUT = httpx.Timeout(20.0, connect=8.0)


class AzureTranslator:
    name = "azure-translator"

    def __init__(self) -> None:
        az = config.AZURE
        if not az.translator_key:
            raise RuntimeError("AZURE_TRANSLATOR_KEY not set")
        self._key = az.translator_key
        self._region = az.translator_region
        self._endpoint = az.translator_endpoint.rstrip("/")

    def _headers(self) -> dict[str, str]:
        h = {"Ocp-Apim-Subscription-Key": self._key, "Content-Type": "application/json"}
        if self._region:
            h["Ocp-Apim-Subscription-Region"] = self._region
        return h

    def detect(self, text: str) -> str:
        url = f"{self._endpoint}/detect?api-version=3.0"
        r = httpx.post(url, headers=self._headers(), json=[{"Text": text[:4000]}], timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()[0]["language"]

    def translate(self, texts: Sequence[str], target: str, source: str = "en") -> list[str]:
        if not texts:
            return []
        url = f"{self._endpoint}/translate?api-version=3.0&from={source}&to={target}"
        # textType=html would let us use <span translate="no">, but the entity
        # lock already guarantees preservation structurally and plain text keeps
        # the round trip lossless.
        payload = [{"Text": t} for t in texts]
        r = httpx.post(url, headers=self._headers(), json=payload, timeout=TIMEOUT)
        r.raise_for_status()
        return [item["translations"][0]["text"] for item in r.json()]


class _AzureOpenAIBase:
    def __init__(self, deployment_attr: str) -> None:
        az = config.AZURE
        if not (az.openai_key and az.openai_endpoint):
            raise RuntimeError("AZURE_OPENAI_KEY / AZURE_OPENAI_ENDPOINT not set")
        deployment = getattr(az, deployment_attr)
        if not deployment:
            raise RuntimeError(f"{deployment_attr} not set")
        self._key = az.openai_key
        self._endpoint = az.openai_endpoint.rstrip("/")
        self._deployment = deployment
        self._version = az.openai_api_version

    def _chat(self, system: str, user: str, temperature: float = 0.0) -> str:
        url = (
            f"{self._endpoint}/openai/deployments/{self._deployment}"
            f"/chat/completions?api-version={self._version}"
        )
        body = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
        }
        r = httpx.post(url, headers={"api-key": self._key}, json=body, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()


SIMPLIFY_SYSTEM = """You rewrite official US National Weather Service emergency text into plain language.

Absolute rules:
1. Tokens of the form [[E7]] are locked entities. Reproduce every one of them \
exactly, once each, in the same meaning position. Never translate, reorder \
inside, renumber, drop, or duplicate them.
2. Add no fact that is not in the input. No advice, no reassurance, no \
explanation of causes, no severity you were not given.
3. Keep every instruction. If the input says to do something, the output says \
to do the same thing.
4. Keep negation. "Do not" must stay "do not".
5. Target a US grade {grade} reading level: short sentences, common words, \
active voice, second person.
6. Output only the rewritten text."""

JUDGE_SYSTEM = """You check whether a rewritten emergency message is fully supported by its source.

Answer with strict JSON only: {"entailed": true|false, "confidence": 0.0-1.0, "reason": "<= 25 words"}

Mark entailed=false if the rewrite:
- states any fact, number, time, place or road not in the source
- drops or reverses an instruction the source gives
- flips a negation
- softens or strengthens the stated severity
Otherwise entailed=true. Fluency and style are irrelevant - judge only factual support."""


class AzureOpenAISimplifier(_AzureOpenAIBase):
    name = "azure-openai-simplify"

    def __init__(self) -> None:
        super().__init__("openai_chat_deployment")

    @property
    def prompt_sha256(self) -> str:
        return hashlib.sha256(SIMPLIFY_SYSTEM.encode()).hexdigest()

    def simplify(self, text: str, target_grade: float = 7.0, lang: str = "en",
                 protect: frozenset[str] = frozenset()) -> str:
        system = SIMPLIFY_SYSTEM.replace("{grade}", str(int(target_grade)))
        if protect:
            system += ("\n7. These are official terms of record. Never replace or paraphrase "
                       "them: " + ", ".join(sorted(protect)) + ".")
        return self._chat(system, text)


class AzureOpenAIJudge(_AzureOpenAIBase):
    name = "azure-openai-judge"
    llm_backed = True

    def __init__(self) -> None:
        super().__init__("openai_chat_deployment")

    def entails(self, source: str, candidate: str) -> tuple[bool, float, str]:
        user = f"SOURCE:\n{source}\n\nREWRITE:\n{candidate}"
        raw = self._chat(JUDGE_SYSTEM, user)
        try:
            start, end = raw.find("{"), raw.rfind("}")
            data = json.loads(raw[start : end + 1])
            return bool(data["entailed"]), float(data.get("confidence", 0.5)), str(data.get("reason", ""))[:200]
        except Exception:
            # A judge that cannot be parsed is a failed check, never a pass.
            # Abstention is the safe direction (brief section 3.1).
            return False, 0.0, f"judge response unparseable: {raw[:120]}"


ESCALATION_SYSTEM = """You screen a disaster survivor's free-text message for cases a human caseworker must handle.

Return strict JSON only: {"labels": [...]}, using only these labels:
- danger_now: someone may be in physical danger or need emergency care now
- self_harm: thoughts of suicide or self-harm
- abuse: domestic violence, abuse, or feeling unsafe with someone
- immigration: questions or worries about immigration status
- identity_theft: an application or account they did not make
- fraud: someone asking for money, fees, or personal details to "help"
- high_impact: a denial, appeal, debt, eviction, or foreclosure

Include every label that plausibly applies, including indirect or non-English wording.
When unsure, include the label. Return {"labels": []} only when none apply."""


class AzureOpenAIEscalationClassifier(_AzureOpenAIBase):
    """Suggests escalation labels. It can only add: see escalation.model_triggers."""

    name = "azure-openai-escalation"

    def __init__(self) -> None:
        super().__init__("openai_chat_deployment")

    def classify(self, text: str) -> list[str]:
        raw = self._chat(ESCALATION_SYSTEM, text)
        start, end = raw.find("{"), raw.rfind("}")
        labels = json.loads(raw[start : end + 1]).get("labels", [])
        return [str(label) for label in labels]


class AzureOpenAIEmbedder(_AzureOpenAIBase):
    name = "azure-openai-embeddings"
    semantic = True

    def __init__(self) -> None:
        super().__init__("openai_embed_deployment")

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        url = (
            f"{self._endpoint}/openai/deployments/{self._deployment}"
            f"/embeddings?api-version={self._version}"
        )
        r = httpx.post(url, headers={"api-key": self._key}, json={"input": list(texts)}, timeout=TIMEOUT)
        r.raise_for_status()
        return [d["embedding"] for d in r.json()["data"]]


class AzureSpeech:
    name = "azure-speech"

    def __init__(self) -> None:
        az = config.AZURE
        if not (az.speech_key and az.speech_region):
            raise RuntimeError("AZURE_SPEECH_KEY / AZURE_SPEECH_REGION not set")
        self._key = az.speech_key
        self._region = az.speech_region

    def synthesize(self, text: str, lang: str) -> tuple[bytes, str]:
        voice = config.SUPPORTED_LANGUAGES.get(lang, {}).get("voice", "en-US-JennyNeural")
        locale = "-".join(voice.split("-")[:2])
        ssml = (
            f"<speak version='1.0' xml:lang='{locale}'>"
            f"<voice name='{voice}'><prosody rate='-8%'>"
            f"{_xml_escape(text)}"
            f"</prosody></voice></speak>"
        )
        url = f"https://{self._region}.tts.speech.microsoft.com/cognitiveservices/v1"
        headers = {
            "Ocp-Apim-Subscription-Key": self._key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
            "User-Agent": "last-mile-alert",
        }
        r = httpx.post(url, headers=headers, content=ssml.encode("utf-8"), timeout=TIMEOUT)
        r.raise_for_status()
        return r.content, "audio/mpeg"


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


class AzureContentSafety:
    name = "azure-content-safety"

    def __init__(self) -> None:
        az = config.AZURE
        if not (az.content_safety_key and az.content_safety_endpoint):
            raise RuntimeError("AZURE_CONTENT_SAFETY_* not set")
        self._key = az.content_safety_key
        self._endpoint = az.content_safety_endpoint.rstrip("/")

    def check(self, text: str) -> tuple[bool, list[str]]:
        url = f"{self._endpoint}/contentsafety/text:analyze?api-version=2023-10-01"
        r = httpx.post(
            url,
            headers={"Ocp-Apim-Subscription-Key": self._key, "Content-Type": "application/json"},
            json={"text": text[:10000]},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        flags = [
            c["category"]
            for c in r.json().get("categoriesAnalysis", [])
            if c.get("severity", 0) >= 4
        ]
        return (not flags), flags


class KeyVaultSigner:
    """Asymmetric manifest signing.

    Uses azure-identity + azure-keyvault-keys when they are installed. The
    import is inside __init__ so the package is never a hard dependency.
    """

    name = "azure-key-vault"
    algorithm = "RS256"

    def __init__(self) -> None:
        az = config.AZURE
        if not (az.keyvault_url and az.keyvault_key_name):
            raise RuntimeError("AZURE_KEYVAULT_URL / AZURE_KEYVAULT_KEY_NAME not set")
        from azure.identity import DefaultAzureCredential  # type: ignore
        from azure.keyvault.keys import KeyClient  # type: ignore
        from azure.keyvault.keys.crypto import CryptographyClient  # type: ignore

        cred = DefaultAzureCredential()
        client = KeyClient(vault_url=az.keyvault_url, credential=cred)
        key = client.get_key(az.keyvault_key_name)
        self._crypto = CryptographyClient(key, credential=cred)
        self._jwk = key.key
        self.key_id = key.id

    def public_jwk(self) -> dict:
        """The public half, so anyone can verify a manifest without Key Vault access."""
        import base64

        def b64url(value: bytes) -> str:
            return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

        return {"kty": "RSA", "alg": self.algorithm, "kid": self.key_id,
                "n": b64url(self._jwk.n), "e": b64url(self._jwk.e)}

    def sign(self, payload: bytes) -> str:
        from azure.keyvault.keys.crypto import SignatureAlgorithm  # type: ignore

        digest = hashlib.sha256(payload).digest()
        result = self._crypto.sign(SignatureAlgorithm.rs256, digest)
        return result.signature.hex()

    def verify(self, payload: bytes, signature: str) -> bool:
        from azure.keyvault.keys.crypto import SignatureAlgorithm  # type: ignore

        digest = hashlib.sha256(payload).digest()
        result = self._crypto.verify(SignatureAlgorithm.rs256, digest, bytes.fromhex(signature))
        return bool(result.is_valid)
