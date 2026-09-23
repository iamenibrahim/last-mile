from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class LockedEntity:
    token: str
    value: str
    kind: str


@dataclass(frozen=True)
class LockedText:
    masked: str
    entities: tuple[LockedEntity, ...]


_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "url",
        re.compile(r"https?://[^\s<>\]\)]+", re.IGNORECASE),
    ),
    (
        "phone",
        re.compile(r"(?<!\w)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\w)"),
    ),
    (
        "road",
        re.compile(
            r"\b(?:I|US|VA)[-\s]?\d{1,3}\b|\b(?:Route|Exit)\s+\d{1,4}[A-Z]?\b",
            re.IGNORECASE,
        ),
    ),
    (
        "time",
        re.compile(
            r"\b(?:\d{1,2}:\d{2}\s*(?:AM|PM)?|\d{1,2}\s*(?:AM|PM)|noon|midnight)\s*(?:EDT|EST|UTC)?\b",
            re.IGNORECASE,
        ),
    ),
    (
        "date",
        re.compile(
            r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|"
            r"January|February|March|April|May|June|July|August|September|October|November|December)"
            r"(?:\s+\d{1,2}(?:,\s*\d{4})?)?\b"
        ),
    ),
    (
        "measurement",
        re.compile(
            r"(?<!\w)\d+(?:\.\d+)?\s?(?:feet|foot|ft|inches|inch|in|mph|miles?|km|%)(?!\w)",
            re.IGNORECASE,
        ),
    ),
    ("number", re.compile(r"(?<![\w\[])\d+(?:\.\d+)?(?![\w\]])")),
)


def _gazetteer_pattern(places: Iterable[str]) -> re.Pattern[str] | None:
    values = sorted({p.strip() for p in places if p and p.strip()}, key=len, reverse=True)
    if not values:
        return None
    return re.compile(r"\b(?:" + "|".join(re.escape(v) for v in values) + r")\b", re.IGNORECASE)


def lock_entities(text: str, places: Iterable[str] = ()) -> LockedText:
    """Replace critical spans with sentinels before any generative transformation.

    Overlaps are resolved deterministically: specific patterns run before general numbers.
    The function is deliberately model-independent so preservation is structural.
    """

    spans: list[tuple[int, int, str]] = []
    patterns = list(_PATTERNS)
    gazetteer = _gazetteer_pattern(places)
    if gazetteer:
        patterns.insert(2, ("place", gazetteer))

    for kind, pattern in patterns:
        for match in pattern.finditer(text):
            start, end = match.span()
            if any(start < prior_end and end > prior_start for prior_start, prior_end, _ in spans):
                continue
            spans.append((start, end, kind))

    spans.sort(key=lambda item: item[0])
    chunks: list[str] = []
    entities: list[LockedEntity] = []
    cursor = 0
    for index, (start, end, kind) in enumerate(spans, start=1):
        token = f"[[E{index}]]"
        chunks.extend((text[cursor:start], token))
        entities.append(LockedEntity(token=token, value=text[start:end], kind=kind))
        cursor = end
    chunks.append(text[cursor:])
    return LockedText(masked="".join(chunks), entities=tuple(entities))


def restore_entities(masked_text: str, entities: Iterable[LockedEntity]) -> str:
    restored = masked_text
    for entity in entities:
        restored = restored.replace(entity.token, entity.value)
    return restored


def entity_integrity(masked_output: str, entities: Iterable[LockedEntity]) -> dict:
    entities = tuple(entities)
    failures: list[dict[str, str | int]] = []
    for entity in entities:
        count = masked_output.count(entity.token)
        if count != 1:
            failures.append({"token": entity.token, "expected": 1, "actual": count})
    unknown = sorted(set(re.findall(r"\[\[E\d+\]\]", masked_output)) - {e.token for e in entities})
    for token in unknown:
        failures.append({"token": token, "expected": 0, "actual": masked_output.count(token)})
    return {"passed": not failures, "failures": failures, "checked": len(entities)}
