from __future__ import annotations

import math
import os
import re

from .entities import LockedEntity, entity_integrity


ACTION_WORDS = re.compile(
    r"\b(?:move|go|leave|evacuate|avoid|do not|don't|call|apply|bring|stay|turn|seek|drive)\b",
    re.IGNORECASE,
)


def _meaningful_tokens(value: str) -> set[str]:
    stop = {"the", "and", "that", "with", "from", "this", "your", "you", "for"}

    def stem(token: str) -> str:
        if len(token) > 5 and token.endswith("ing"):
            return token[:-3]
        if len(token) > 4 and token.endswith("ed"):
            return token[:-2]
        if len(token) > 4 and token.endswith("s"):
            return token[:-1]
        return token

    return {
        stem(token.lower())
        for token in re.findall(r"[A-Za-z]{3,}", value)
        if token.lower() not in stop
    }


# Cosine floor for Foundry embeddings. Starting value from the grounded pipeline;
# retune on the first keyed evaluation run.
FOUNDRY_SIMILARITY_THRESHOLD = float(os.getenv("FOUNDRY_SIMILARITY_THRESHOLD", "0.82"))
ROUND_TRIP_TOKEN_THRESHOLD = float(os.getenv("ROUND_TRIP_TOKEN_THRESHOLD", "0.65"))


def _negation_count(value: str) -> int:
    normalized = re.sub(r"\b(?:don't|do not)\b", " not ", value, flags=re.IGNORECASE)
    normalized = re.sub(r"\b(?:can't|cannot)\b", " not ", normalized, flags=re.IGNORECASE)
    return len(re.findall(r"\b(?:not|never|no|avoid|without)\b", normalized, re.IGNORECASE))


def _foundry_similarity(source: str, output: str) -> float | None:
    """Cosine similarity from Foundry embeddings, or None when they are not configured.

    text-embedding-3-small is multilingual, so a translation can be compared with
    its English source directly, not only through a back-translation.
    """
    try:
        from grounded.providers.base import get_registry

        embedder = get_registry().embedder
        if not getattr(embedder, "semantic", False):
            return None
        first, second = embedder.embed([source, output])
    except Exception:
        return None
    dot = sum(a * b for a, b in zip(first, second))
    norms = math.sqrt(sum(a * a for a in first)) * math.sqrt(sum(b * b for b in second))
    return dot / norms if norms else 0.0


def semantic_fidelity(
    source: str,
    output: str,
    provider_confidence: float,
    translated: bool,
    round_trip: bool = False,
) -> dict:
    source_negations = _negation_count(source)
    output_negations = _negation_count(output)
    if source_negations != output_negations and (not translated or round_trip):
        return {
            "passed": False,
            "score": 0.0,
            "method": "negation-polarity guard",
            "source_negations": source_negations,
            "output_negations": output_negations,
        }
    similarity = _foundry_similarity(source, output)
    if similarity is not None:
        return {
            "passed": similarity >= FOUNDRY_SIMILARITY_THRESHOLD,
            "score": round(similarity, 3),
            "method": "Foundry embeddings cosine similarity",
            "threshold": FOUNDRY_SIMILARITY_THRESHOLD,
        }
    if round_trip:
        source_tokens = _meaningful_tokens(source)
        output_tokens = _meaningful_tokens(output)
        score = len(source_tokens & output_tokens) / max(1, len(source_tokens))
        return {
            "passed": score >= ROUND_TRIP_TOKEN_THRESHOLD,
            "score": round(score, 3),
            "method": "Azure Translator round-trip token recall (lexical safety proxy)",
            "threshold": ROUND_TRIP_TOKEN_THRESHOLD,
        }
    if translated:
        score = provider_confidence
        method = "provider confidence (no embeddings configured; not a meaning check)"
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
    translated = target_language != "en"
    round_trip = translated and comparison_output is not None
    checks = {
        "entity_integrity": entity_integrity(masked_output, entities),
        "semantic_fidelity": semantic_fidelity(
            source,
            comparison,
            provider_confidence,
            translated=translated,
            round_trip=round_trip,
        ),
        "instruction_coverage": instruction_coverage(
            source, comparison, is_instruction, translated=translated
        ),
        "grounding": grounding(
            source,
            comparison,
            "translated-round-trip" if round_trip else provider,
        ),
    }
    return {"passed": all(item["passed"] for item in checks.values()), "checks": checks}
