from __future__ import annotations

import hashlib
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

from .config import settings
from .entities import lock_entities, restore_entities
from .manifest import build_manifest
from .providers import local
from .verify import verify_segment


LANGUAGES = {
    "en": "English",
    "es": "Spanish",
    "ar": "Arabic",
    "prs": "Dari",
    "tl": "Tagalog",
}


def split_segments(value: str) -> list[tuple[str, int, int]]:
    segments: list[tuple[str, int, int]] = []
    for match in re.finditer(r"[^\n.!?]+(?:[.!?]+|$)", value):
        text = match.group(0).strip()
        if text:
            start = match.start() + len(match.group(0)) - len(match.group(0).lstrip())
            segments.append((text, start, start + len(text)))
    return segments or ([(value, 0, len(value))] if value else [])


def _provider_transform(masked: str, language: str, grade: int) -> tuple[str, dict]:
    if language == "en" and settings.foundry_enabled:
        try:
            from .providers.azure_foundry import simplify

            return simplify(masked, grade)
        except Exception as error:
            text, meta = local.translate(masked, language)
            meta["fallback_reason"] = type(error).__name__
            return text, meta
    if language != "en" and settings.translator_enabled:
        try:
            from .providers.azure_translator import translate

            return translate(masked, language)
        except Exception as error:
            text, meta = local.translate(masked, language)
            meta["fallback_reason"] = type(error).__name__
            return text, meta
    return local.translate(masked, language)


def _reading_grade(text: str) -> float:
    words = re.findall(r"[A-Za-z]+", text)
    sentences = max(1, len(re.findall(r"[.!?]+", text)))
    if not words:
        return 0.0

    def syllables(word: str) -> int:
        groups = re.findall(r"[aeiouy]+", word.lower())
        count = max(1, len(groups))
        if word.lower().endswith("e") and count > 1:
            count -= 1
        return count

    total_syllables = sum(syllables(word) for word in words)
    return round(max(0.0, 0.39 * (len(words) / sentences) + 11.8 * (total_syllables / len(words)) - 15.59), 1)


def transform_alert(alert: dict, language: str = "es", grade: int = 6, simulate_failure: bool = False) -> dict:
    properties = alert.get("properties", {})
    places = [part.strip() for part in properties.get("areaDesc", "").split(";")]
    source_sections = [
        ("headline", properties.get("headline", ""), False),
        ("description", properties.get("description", ""), False),
        ("instruction", properties.get("instruction", ""), True),
    ]
    chain: list[dict] = []
    prepared: list[dict] = []
    for section, value, is_instruction in source_sections:
        for index, (segment, start, end) in enumerate(split_segments(value), start=1):
            locked = lock_entities(segment, places)
            prepared.append(
                {
                    "id": f"{section}-{index}",
                    "section": section,
                    "source": segment,
                    "start": start,
                    "end": end,
                    "is_instruction": is_instruction,
                    "locked": locked,
                }
            )

    simulation_target = next(
        (item["id"] for item in prepared if item["locked"].entities), None
    )

    def process(item: dict) -> dict:
        segment = item["source"]
        locked = item["locked"]
        transformed, provider_meta = _provider_transform(locked.masked, language, grade)
        if simulate_failure and item["id"] == simulation_target:
            transformed = transformed.replace(locked.entities[0].token, "", 1)
        restored = restore_entities(transformed, locked.entities)
        comparison_output = None
        if provider_meta.get("back_translation"):
            comparison_output = restore_entities(
                provider_meta["back_translation"], locked.entities
            )
        verification = verify_segment(
            source=segment,
            masked_output=transformed,
            restored_output=restored,
            entities=locked.entities,
            provider_confidence=float(provider_meta.get("confidence", 0.96)),
            target_language=language,
            provider=provider_meta.get("engine", "unknown"),
            is_instruction=item["is_instruction"],
            comparison_output=comparison_output,
        )
        if provider_meta.get("engine") == "microsoft-foundry" and settings.foundry_enabled:
            try:
                from .providers.azure_foundry import judge_entailment

                foundry_grounding = judge_entailment(segment, restored)
                number_guard = verification["checks"]["grounding"]
                verification["checks"]["grounding"] = {
                    "passed": foundry_grounding["passed"]
                    and not number_guard.get("added_numbers"),
                    "method": "Microsoft Foundry strict entailment judge + no-new-number guard",
                    "reason": foundry_grounding.get("reason"),
                    "added_numbers": number_guard.get("added_numbers", []),
                }
                verification["passed"] = all(
                    check["passed"] for check in verification["checks"].values()
                )
            except Exception as error:
                verification["checks"]["grounding"] = {
                    "passed": False,
                    "method": "Microsoft Foundry entailment judge",
                    "reason": f"Judge unavailable: {type(error).__name__}",
                }
                verification["passed"] = False
        output_safety = {"passed": True, "mode": "not-configured"}
        if verification["passed"] and settings.content_safety_enabled:
            try:
                from .providers.azure_content_safety import analyze

                output_safety = {**analyze(restored), "mode": "azure-ai-content-safety"}
            except Exception as error:
                output_safety = {
                    "passed": False,
                    "mode": "azure-ai-content-safety",
                    "reason": f"Guard unavailable: {type(error).__name__}",
                }
            if not output_safety["passed"]:
                verification["passed"] = False
        status = "translated_verified" if verification["passed"] else "verbatim_abstained"
        output = restored if verification["passed"] else segment
        reason = None
        if not verification["passed"]:
            reason = next(
                (
                    name
                    for name, result in verification["checks"].items()
                    if not result["passed"]
                ),
                "output_safety",
            )
        return {
            "id": item["id"],
            "section": item["section"],
            "source": segment,
            "output": output,
            "status": status,
            "reason": reason,
            "source_offset": {"start": item["start"], "end": item["end"]},
            "entities": [asdict(entity) for entity in locked.entities],
            "verification": verification,
            "output_safety": output_safety,
            "provider": provider_meta,
        }

    max_workers = max(1, min(len(prepared), int(os.getenv("TRANSFORM_MAX_WORKERS", "4"))))
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="transform") as executor:
        rendered = list(executor.map(process, prepared))
    manifest_segments = [
        {"id": item["id"], "status": item["status"], "reason": item["reason"]}
        for item in rendered
    ]

    instruction_present = bool(properties.get("instruction", "").strip())
    output_text = "\n".join(item["output"] for item in rendered)
    providers = sorted({item["provider"]["engine"] for item in rendered})
    checks_passed = sum(
        1
        for item in rendered
        for check in item["verification"]["checks"].values()
        if check["passed"]
    )
    checks_failed = sum(
        1
        for item in rendered
        for check in item["verification"]["checks"].values()
        if not check["passed"]
    )
    chain.extend(
        [
            {"step": "entity_lock", "version": "1.0", "entities": sum(len(item["entities"]) for item in rendered)},
            {"step": "translate_simplify", "engine": ", ".join(providers), "target": language},
            {
                "step": "verify",
                "checks_passed": checks_passed,
                "checks_failed": checks_failed,
                "prompt_sha256": hashlib.sha256(b"last-mile-transform-v1").hexdigest(),
            },
            {
                "step": "output_safety",
                "engine": "azure-ai-content-safety" if settings.content_safety_enabled else "not-configured-local-demo",
                "blocked_segments": sum(1 for item in rendered if not item["output_safety"]["passed"]),
            },
        ]
    )
    manifest = build_manifest(alert, chain, manifest_segments, output_text)
    from .protocol import compile_alert_packet

    protocol_packet = compile_alert_packet(alert, rendered, manifest)
    return {
        "source_alert": alert,
        "language": language,
        "language_name": LANGUAGES.get(language, language),
        "target_grade": grade,
        "source_grade": _reading_grade(" ".join(value for _, value, _ in source_sections)),
        "output_grade": _reading_grade(output_text) if language == "en" else None,
        "instruction_present": instruction_present,
        "instruction_notice": None if instruction_present else "The source alert carried no instructions. No actions were inferred.",
        "segments": rendered,
        "manifest": manifest,
        "protocol_packet": protocol_packet,
        "provider_mode": "microsoft-foundry" if settings.foundry_enabled else "resilient-local-demo",
    }
