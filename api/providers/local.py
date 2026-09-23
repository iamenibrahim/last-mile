from __future__ import annotations

import re


SIMPLE_REPLACEMENTS = {
    "immediately": "now",
    "utilize": "use",
    "residents are advised to": "",
    "motorists should not attempt to": "do not",
    "in the event that": "if",
    "due to the fact that": "because",
    "approximately": "about",
    "precipitation": "rain",
    "inundated": "flooded",
}

SPANISH_PHRASES = {
    "Move to higher ground now.": "Vaya a un terreno más alto ahora.",
    "Do not drive across flooded roads.": "No conduzca por carreteras inundadas.",
    "Avoid": "Evite",
    "near": "cerca de",
    "until": "hasta",
    "Call": "Llame al",
    "only for life-threatening emergencies.": "solo para emergencias que amenazan la vida.",
    "Heavy rain is causing flash flooding in": "La lluvia intensa está causando inundaciones repentinas en",
    "Water may rise": "El agua puede subir",
    "roads and low areas.": "carreteras y zonas bajas.",
    "Flash Flood Warning": "Aviso de inundación repentina",
    "issued for": "emitido para",
    " and ": " y ",
}


def simplify(masked_text: str) -> str:
    result = masked_text
    for source, target in SIMPLE_REPLACEMENTS.items():
        result = re.sub(re.escape(source), target, result, flags=re.IGNORECASE)
    result = re.sub(r"\s+", " ", result).strip()
    return result


def translate(masked_text: str, target_language: str) -> tuple[str, dict]:
    if target_language == "en":
        return simplify(masked_text), {"engine": "deterministic-local", "confidence": 1.0}
    if target_language == "es":
        translated = masked_text
        for source, target in sorted(SPANISH_PHRASES.items(), key=lambda item: len(item[0]), reverse=True):
            translated = translated.replace(source, target)
        changed = translated != masked_text
        return translated, {
            "engine": "curated-demo-cache",
            "confidence": 0.93 if changed else 0.55,
            "cache_notice": "Demo-only cached phrases; configure Azure AI Translator for production.",
        }
    return masked_text, {
        "engine": "local-abstention",
        "confidence": 0.0,
        "reason": "Azure AI Translator is not configured for this language.",
    }
