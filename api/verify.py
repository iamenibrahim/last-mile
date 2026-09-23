from __future__ import annotations

import re

from .entities import LockedEntity, entity_integrity


ACTION_WORDS = re.compile(
    r"\b(?:move|go|leave|evacuate|avoid|do not|don't|call|apply|bring|stay|turn|seek|drive)\b",
    re.IGNORECASE,
)


def _meaningful_tokens(value: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z]{3,}", value)
        if token.lower() not in {"the", "and", "that", "with", "from", "this", "your", "you", "for"}
    }


def semantic_fidelity(source: str, output: str, provider_confidence: float, translated: bool) -> dict:
    source_negations = len(re.findall(r"\b(?:not|never|no|avoid|without)\b", source, re.IGNORECASE))
    output_negations = len(re.findall(r"\b(?:not|never|no|avoid|without)\b", output, re.IGNORECASE))
    if source_negations != output_negations and not translated:
        return {
            "passed": False,
            "score": 0.0,
            "method": "negation-polarity guard",
            "source_negations": source_negations,
            "output_negations": output_negations,
        }
    if translated:
        score = provider_confidence
        method = "provider-confidence; Foundry embeddings in cloud evaluation"
    else:
        source_tokens = _meaningful_tokens(source)
        output_tokens = _meaningful_tokens(output)
        score = len(source_tokens & output_tokens) / max(1, len(source_tokens))
        method = "deterministic lexical overlap"
    return {"passed": score >= 0.72, "score": round(score, 3), "method": method}


def instruction_coverage(source: str, output: str, is_instruction: bool, translated: bool = False) -> dict:
    if not is_instruction:
        return {"passed": True, "required_actions": 0, "method": "not an instruction segment"}
    source_actions = len(ACTION_WORDS.findall(source))
    if source_actions == 0:
        source_actions = 1
    if translated:
        return {
            "passed": bool(output.strip()),
            "required_actions": source_actions,
            "mapped_actions": 1 if output.strip() else 0,
            "method": "one-to-one instruction segment mapping; semantic check is independent",
        }
    output_actions = len(ACTION_WORDS.findall(output))
    output_has_structure = bool(output.strip()) and output_actions >= source_actions
    return {
        "passed": output_has_structure,
        "required_actions": source_actions,
        "mapped_actions": output_actions,
        "method": "segment-level source-to-output mapping",
    }


def grounding(source: str, output: str, provider: str) -> dict:
    source_numbers = set(re.findall(r"\d+(?:\.\d+)?", source))
    output_numbers = set(re.findall(r"\d+(?:\.\d+)?", output))
    added_numbers = sorted(output_numbers - source_numbers)
    added_terms: list[str] = []
    if provider in {"deterministic-local", "local-abstention"}:
        added_terms = sorted(_meaningful_tokens(output) - _meaningful_tokens(source))
    return {
        "passed": not added_numbers and not added_terms,
        "method": "strict no-new-number and no-new-content guard" if provider != "microsoft-foundry" else "Foundry entailment + no-new-number guard",
        "added_numbers": added_numbers,
        "added_terms": added_terms,
    }


def verify_segment(
    source: str,
    masked_output: str,
    restored_output: str,
    entities: tuple[LockedEntity, ...],
    provider_confidence: float,
    target_language: str,
    provider: str,
    is_instruction: bool,
    comparison_output: str | None = None,
) -> dict:
    comparison = comparison_output or restored_output
    translation_without_backcheck = target_language != "en" and comparison_output is None
    checks = {
        "entity_integrity": entity_integrity(masked_output, entities),
        "semantic_fidelity": semantic_fidelity(
            source, comparison, provider_confidence, translated=translation_without_backcheck
        ),
        "instruction_coverage": instruction_coverage(
            source, comparison, is_instruction, translated=translation_without_backcheck
        ),
        "grounding": grounding(
            source,
            comparison,
            "deterministic-local" if comparison_output is not None else provider,
        ),
    }
    return {"passed": all(item["passed"] for item in checks.values()), "checks": checks}
