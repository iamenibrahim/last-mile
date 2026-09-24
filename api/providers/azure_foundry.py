from __future__ import annotations

import json
import urllib.request

from ..config import settings


SYSTEM_PROMPT = """You are the language transformation component of a public emergency system.
Only transform information present in the supplied source. Preserve every sentinel token such as
[[E1]] byte-for-byte and exactly once. Do not add advice, eligibility decisions, phone numbers,
deadlines, or claims. Return JSON only."""


def _chat(messages: list[dict], temperature: float = 0.0) -> dict:
    url = f"{settings.foundry_endpoint}/openai/v1/chat/completions"
    payload = {
        "model": settings.foundry_model,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    headers = {"Content-Type": "application/json"}
    if settings.foundry_api_key:
        headers["api-key"] = settings.foundry_api_key
    else:
        from azure.identity import DefaultAzureCredential  # type: ignore

        token = DefaultAzureCredential().get_token("https://cognitiveservices.azure.com/.default")
        headers["Authorization"] = f"Bearer {token.token}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    # The request uses the configured Microsoft Foundry HTTPS endpoint.
    with urllib.request.urlopen(request, timeout=20) as response:  # nosec B310
        result = json.load(response)
    return json.loads(result["choices"][0]["message"]["content"])


def simplify(masked_text: str, target_grade: int = 6) -> tuple[str, dict]:
    result = _chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": "Rewrite in plain English without adding or removing instructions.",
                        "target_us_grade": target_grade,
                        "source": masked_text,
                        "response_schema": {"text": "string"},
                    }
                ),
            },
        ]
    )
    return result["text"], {"engine": "microsoft-foundry", "model": settings.foundry_model}


def judge_entailment(source: str, output: str) -> dict:
    result = _chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": "Judge whether every factual claim in output is entailed by source.",
                        "source": source,
                        "output": output,
                        "response_schema": {"entailed": "boolean", "reason": "short string"},
                    }
                ),
            },
        ]
    )
    return {"passed": bool(result.get("entailed")), "reason": result.get("reason", "")}


def explain_program(program: dict, matched_needs: list[str]) -> str:
    result = _chat(
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
