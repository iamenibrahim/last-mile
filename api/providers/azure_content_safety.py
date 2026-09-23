from __future__ import annotations

import json
import urllib.request

from ..config import settings


def analyze(text: str) -> dict:
    url = f"{settings.content_safety_endpoint}/contentsafety/text:analyze?api-version=2024-09-01"
    request = urllib.request.Request(
        url,
        data=json.dumps(
            {
                "text": text[:10000],
                "categories": ["Hate", "SelfHarm", "Sexual", "Violence"],
                "outputType": "FourSeverityLevels",
            }
        ).encode("utf-8"),
        headers={
            "Ocp-Apim-Subscription-Key": settings.content_safety_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.load(response)
    severities = {item["category"]: item["severity"] for item in payload.get("categoriesAnalysis", [])}
    return {"passed": all(value < 4 for value in severities.values()), "severities": severities}

