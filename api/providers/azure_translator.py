from __future__ import annotations

import json
import urllib.parse
import urllib.request
import uuid

from ..config import settings


def _request(text: str, source_language: str, target_language: str) -> tuple[str, dict]:
    params = urllib.parse.urlencode(
        {"api-version": "3.0", "from": source_language, "to": target_language}
    )
    url = f"{settings.translator_endpoint}/translate?{params}"
    headers = {
        "Ocp-Apim-Subscription-Key": settings.translator_key,
        "Content-Type": "application/json",
        "X-ClientTraceId": str(uuid.uuid4()),
    }
    if settings.translator_region:
        headers["Ocp-Apim-Subscription-Region"] = settings.translator_region
    request = urllib.request.Request(
        url,
        data=json.dumps([{"text": text}]).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        payload = json.load(response)
    return payload[0]["translations"][0]["text"], payload[0]


def translate(masked_text: str, target_language: str) -> tuple[str, dict]:
    translated, forward = _request(masked_text, "en", target_language)
    back_translation, _ = _request(translated, target_language, "en")
    return translated, {
        "engine": "azure-ai-translator",
        "confidence": 0.9,
        "detected_language": forward.get("detectedLanguage", {}).get("language", "en"),
        "back_translation": back_translation,
        "semantic_method": "Azure AI Translator round-trip agreement",
    }
