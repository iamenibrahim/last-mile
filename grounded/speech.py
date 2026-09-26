"""Spoken output.

Brief section 6: do not skip TTS. A meaningful share of the target population
has low literacy in any language, and twenty seconds of spoken Dari beats a
perfect paragraph.

The spoken script is assembled from *verified* segments only. An abstained
segment is not read aloud in the target language - reading out English the
listener cannot parse, in a target-language voice, is worse than silence. In
its place the audio carries a fixed notice, drawn from a curated per-language
table and never from a model, telling the listener that part of the message is
shown only in English and how to get an interpreter.
"""

from __future__ import annotations

import re

from . import config
from .providers.base import get_registry
from .store import get_store

# Fixed strings. Hand-written per language, never generated, so they cannot
# drift and never need to abstain.
ABSTENTION_NOTICE: dict[str, str] = {
    "en": "Part of this message could not be safely translated and is shown in English only. "
          "Call the interpreter line for help.",
    "es": "Parte de este mensaje no se pudo traducir de forma segura y se muestra solo en ingles. "
          "Llame a la linea de interpretes para obtener ayuda.",
    "tl": "May bahagi ng mensaheng ito na hindi ligtas na naisalin at nakasulat lamang sa Ingles. "
          "Tumawag sa linya ng interpreter para sa tulong.",
    "ar": "جزء من هذه الرسالة "
          "لم يتم ترجمته ويظهر "
          "بالإنجليزية فقط.",
    "prs": "بخشی از این پیام "
           "ترجمه نشد و فقط به "
           "انگلیسی است.",
}

ACTIONS_LEAD: dict[str, str] = {
    "en": "What to do:",
    "es": "Que hacer:",
    "tl": "Ano ang gagawin:",
    "ar": "ماذا تفعل:",
    "prs": "چه کار کنید:",
}


def build_script(render: dict, household: dict | None = None, max_chars: int = 2200) -> str:
    """Assemble what the voice actually says. Position first, then actions."""
    parts: list[str] = []

    if household and household.get("plain_statement"):
        # Always spoken in English: it is generated from geometry by this
        # system, so it carries no translation risk, but it is also the one
        # line a non-English speaker most needs. The rendered page shows it in
        # the target language; the audio leads with it either way.
        parts.append(household["plain_statement"])

    verified = [s for s in render.get("segments", [])
                if s["status"] in ("translated_verified", "source_verified")]
    headline = next((s for s in verified if s["role"] == "headline"), None)
    if headline:
        parts.append(headline["output_text"])

    lang = render.get("language", "en")

    steps = [s for s in render.get("steps", [])
             if s["status"] in ("translated_verified", "source_verified")]
    if steps:
        parts.append(ACTIONS_LEAD.get(lang, ACTIONS_LEAD["en"]))
        for i, s in enumerate(steps, start=1):
            parts.append(f"{i}. {s['output_text']}")

    body = [s for s in verified if s["role"] == "description"]
    for s in body[:6]:
        label = s.get("section_label")
        parts.append(f"{label}. {s['output_text']}" if label else s["output_text"])

    if render.get("abstained_count"):
        parts.append(ABSTENTION_NOTICE.get(lang, ABSTENTION_NOTICE["en"]))

    if render.get("no_instructions_in_source"):
        parts.append(
            "The source alert gave no instructions. No actions are listed because none were issued."
        )

    script = " ".join(p.strip() for p in parts if p and p.strip())
    script = re.sub(r"\s+", " ", script).strip()
    return script[:max_chars]


def synthesize_script(render_id: str, lang: str, script: str) -> dict:
    """Speak an already-assembled script and store it under the render id."""
    registry = get_registry()
    script = re.sub(r"\s+", " ", script or "").strip()[:2400]
    if not script:
        return {"ok": False, "reason": "empty script", "engine": registry.speech.name}
    try:
        blob, mime = registry.speech.synthesize(script, lang)
    except Exception as exc:
        return {"ok": False, "reason": f"{type(exc).__name__}: {exc}", "engine": registry.speech.name}
    get_store().put_audio(render_id, lang, blob, mime)
    return {
        "ok": True, "engine": registry.speech.name, "mime": mime, "bytes": len(blob),
        "script": script, "url": f"api/audio/{render_id}?lang={lang}",
        "note": None if registry.speech.name.startswith("azure") else
        "local fallback voice: Windows SAPI where available, otherwise a placeholder tone.",
    }


def navigator_script(render: dict) -> str:
    """Handoff first, then the answer, then how to apply, then one fraud line.
    Only verified segments are read in the target language; if anything was
    withheld, the fixed notice says so."""
    lang = render.get("language", "en")
    segs = [s for s in render.get("segments", [])
            if s["status"] in ("translated_verified", "source_verified")]
    by_role: dict[str, list[dict]] = {}
    for s in segs:
        by_role.setdefault(s["role"], []).append(s)
    parts: list[str] = []
    for role in ("escalation", "channel", "status"):
        parts += [s["output_text"] for s in by_role.get(role, [])]
    for s in segs:
        if s["role"] == "program_name":
            parts.append(s["output_text"])
        elif s["role"] == "claim" and (s.get("meta") or {}).get("claim_kind") in ("how_to_apply", "deadline"):
            parts.append(s["output_text"])
    parts += [s["output_text"] for s in by_role.get("fraud", [])[:1]]
    if render.get("abstained_count"):
        parts.append(ABSTENTION_NOTICE.get(lang, ABSTENTION_NOTICE["en"]))
    return " ".join(parts)


def synthesize_for_render(render: dict, household: dict | None = None) -> dict:
    """Render to audio and stash it against the render id."""
    registry = get_registry()
    lang = render.get("language", "en")
    script = build_script(render, household)
    if not script:
        return {"ok": False, "reason": "empty script", "engine": registry.speech.name}

    try:
        blob, mime = registry.speech.synthesize(script, lang)
    except Exception as exc:
        return {"ok": False, "reason": f"{type(exc).__name__}: {exc}",
                "engine": registry.speech.name, "script": script}

    get_store().put_audio(render["render_id"], lang, blob, mime)
    return {
        "ok": True,
        "engine": registry.speech.name,
        "mime": mime,
        "bytes": len(blob),
        "script": script,
        "voice": config.SUPPORTED_LANGUAGES.get(lang, {}).get("voice"),
        "url": f"api/audio/{render['render_id']}?lang={lang}",
        "note": (
            None
            if registry.speech.name.startswith("azure")
            else "local fallback voice: Windows SAPI where available, otherwise a "
                 "placeholder tone. Not production speech, and not presented as such."
        ),
    }
