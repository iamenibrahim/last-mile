from __future__ import annotations

import hashlib
import json
import random
import threading
import time
from collections import OrderedDict

import httpx

from ..config import settings


SYSTEM_PROMPT = """You are the language transformation component of a public emergency system.
Only transform information present in the supplied source. Preserve every sentinel token such as
[[E1]] byte-for-byte and exactly once. Do not add advice, eligibility decisions, phone numbers,
deadlines, or claims. Return JSON only."""

# Small deployments follow a worked example far more reliably than a described
# schema: asked for a schema, Phi-4-mini invents its own key names and strips the
# brackets off the sentinels, which fails the entity check and forces a fallback.
# Two short exchanges pin both the shape and the bracket handling. Neither
# example resembles a real alert sentence, so the model rewrites the input rather
# than answering it.
SIMPLIFY_EXAMPLES = [
    {"role": "user", "content": "A Tornado Warning remains in effect until [[E1]] for [[E2]]."},
    {
        "role": "assistant",
        "content": '{"text": "A tornado warning is in effect until [[E1]] for [[E2]]."}',
    },
    {
        "role": "user",
        "content": "Residents should refrain from utilizing elevators during the outage.",
    },
    {"role": "assistant", "content": '{"text": "Do not use elevators during the outage."}'},
]

JUDGE_EXAMPLES = [
    {
        "role": "user",
        "content": '{"source": "Move to higher ground.", "output": "Go uphill now, and call 911."}',
    },
    {
        "role": "assistant",
        "content": '{"entailed": false, "reason": "the phone number is not in the source"}',
    },
]

TIMEOUT = 20.0
MAX_ATTEMPTS = 3
RETRY_STATUS = {408, 429, 500, 502, 503, 504}
CACHE_LIMIT = 512

_CLIENT: httpx.Client | None = None
_CLIENT_LOCK = threading.Lock()
_TOKEN: tuple[str, float] | None = None
_TOKEN_LOCK = threading.Lock()
_CACHE: OrderedDict[str, dict] = OrderedDict()
_CACHE_LOCK = threading.Lock()


def _client() -> httpx.Client:
    """One keep-alive client for the whole process.

    Every segment used to pay a fresh TLS handshake. The transform makes two
    calls per segment and runs segments in parallel, so reusing connections
    removes the largest fixed cost per call.
    """
    global _CLIENT
    if _CLIENT is None:
        with _CLIENT_LOCK:
            if _CLIENT is None:
                _CLIENT = httpx.Client(
                    timeout=TIMEOUT,
                    limits=httpx.Limits(max_keepalive_connections=16, max_connections=16),
                )
    return _CLIENT


def _auth_headers() -> dict:
    if settings.foundry_api_key:
        return {"api-key": settings.foundry_api_key}
    global _TOKEN
    with _TOKEN_LOCK:
        if _TOKEN is None or _TOKEN[1] - time.time() < 300:
            from azure.identity import DefaultAzureCredential  # type: ignore

            token = DefaultAzureCredential().get_token(
                "https://cognitiveservices.azure.com/.default"
            )
            _TOKEN = (token.token, float(token.expires_on))
        return {"Authorization": f"Bearer {_TOKEN[0]}"}


def _cache_key(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _cached(key: str) -> dict | None:
    with _CACHE_LOCK:
        if key in _CACHE:
            _CACHE.move_to_end(key)
            return json.loads(json.dumps(_CACHE[key]))
    return None


def _remember(key: str, value: dict) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = value
        _CACHE.move_to_end(key)
        while len(_CACHE) > CACHE_LIMIT:
            _CACHE.popitem(last=False)


def cache_clear() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


def _retry_after(response: httpx.Response, attempt: int) -> float:
    header = response.headers.get("Retry-After", "")
    try:
        return min(float(header), 8.0)
    except ValueError:
        return min(0.5 * (2**attempt) + random.uniform(0, 0.25), 8.0)  # nosec B311


def _chat(messages: list[dict], temperature: float = 0.0) -> tuple[dict, bool]:
    """Call the deployment and return (parsed JSON, whether it came from cache).

    At temperature 0 the deployment is asked for a deterministic answer, so an
    identical request may be served from an in-process cache. The cache is
    reported to the caller rather than hidden: a cached segment is still a real
    Foundry result, but it is not a fresh round trip and the manifest says so.
    """
    url = f"{settings.foundry_endpoint}/openai/v1/chat/completions"
    payload = {
        "model": settings.foundry_model,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    key = _cache_key(payload) if temperature == 0.0 else ""
    if key:
        hit = _cached(key)
        if hit is not None:
            return hit, True

    headers = {"Content-Type": "application/json", **_auth_headers()}
    last_error: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            # The request uses the configured Microsoft Foundry HTTPS endpoint.
            response = _client().post(url, json=payload, headers=headers)
        except httpx.HTTPError as error:
            last_error = error
            if attempt == MAX_ATTEMPTS - 1:
                raise
            time.sleep(min(0.5 * (2**attempt), 4.0))
            continue
        if response.status_code in RETRY_STATUS and attempt < MAX_ATTEMPTS - 1:
            time.sleep(_retry_after(response, attempt))
            continue
        response.raise_for_status()
        result = json.loads(response.json()["choices"][0]["message"]["content"])
        if key:
            _remember(key, result)
        return result, False
    raise last_error or RuntimeError("Foundry request failed")


def _only_text(result: dict) -> str:
    """Pull the rewritten sentence out of whatever shape came back.

    The deployment occasionally wraps the answer or renames the key. Reading a
    lone string value is a shape repair, never a content one: nothing is
    rewritten here, and whatever is returned still has to pass the entity,
    fidelity, coverage and grounding checks before a resident sees it.
    """
    if isinstance(result.get("text"), str):
        return result["text"]
    nested = result.get("response_schema")
    if isinstance(nested, dict) and isinstance(nested.get("text"), str):
        return nested["text"]
    strings = [value for value in result.values() if isinstance(value, str)]
    if len(strings) == 1:
        return strings[0]
    raise KeyError("no single rewritten sentence in the response")


def simplify(masked_text: str, target_grade: int = 6) -> tuple[str, dict]:
    result, cached = _chat(
        [
            {
                "role": "system",
                "content": f"{SYSTEM_PROMPT}\nAim for a US grade {target_grade} reading level.\n"
                "Rewrite only the sentence you are given. Do not append reassurance, "
                "encouragement or a closing line such as 'stay safe' or 'stay alert'.\n"
                'Reply with one JSON object whose only key is "text".',
            },
            *SIMPLIFY_EXAMPLES,
            {"role": "user", "content": masked_text},
        ]
    )
    return _only_text(result), {
        "engine": "microsoft-foundry",
        "model": settings.foundry_model,
        "cached": cached,
    }


def judge_entailment(source: str, output: str) -> dict:
    result, cached = _chat(
        [
            {
                "role": "system",
                "content": "You check whether every factual claim in the output is entailed by the "
                "source. An output that adds anything the source does not say is not entailed. "
                'Reply with one JSON object: {"entailed": true or false, "reason": "short string"}.',
            },
            *JUDGE_EXAMPLES,
            {"role": "user", "content": json.dumps({"source": source, "output": output})},
        ]
    )
    return {
        "passed": bool(result.get("entailed")),
        "reason": result.get("reason", ""),
        "cached": cached,
    }


def explain_program(program: dict, matched_needs: list[str]) -> str:
    result, _ = _chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": "Explain in two short plain-language sentences why this official program may fit. Never promise eligibility.",
                        "program": {
                            "name": program["name"],
                            "summary": program["summary"],
                            "eligibility": program["eligibility"],
                        },
                        "matched_needs": matched_needs,
                        "response_schema": {"text": "string"},
                    }
                ),
            },
        ]
    )
    return result["text"]
