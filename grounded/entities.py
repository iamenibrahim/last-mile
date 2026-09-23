"""Entity locking: the structural half of the abstention guarantee.

Brief section 3.1, Stage 1. Before any model sees the text, the spans that must
survive verbatim are lifted out and replaced with sentinels. The model is then
architecturally unable to paraphrase a road number, because it never receives
one. Preservation is a property of the pipeline, not a hope about the prompt.

What gets locked (brief section 3.1):
    numbers and measurements, times and timezone markers, road designators,
    place names, river gauge and stream names, phone numbers, URLs, addresses.

Two details that are easy to get wrong and that the tests pin down:

  * Every *occurrence* gets its own sentinel. Two mentions of "I-81" become
    [[E3]] and [[E9]], never one sentinel used twice, because the integrity
    check is "each sentinel appears exactly once" - a check that silently
    breaks if sentinels are shared.

  * Matches are resolved to a non-overlapping set by priority then length, so
    "US-58" locks as one road entity rather than shattering into a bare number.

Unit localisation: restoring English "3 feet" into a Dari paragraph is accurate
but unreadable. `unit_lang` optionally translates only the *unit word* from a
curated per-language table - never a model - while the numeral itself stays
locked. The number, which is the part that gets people killed, keeps its
structural guarantee either way.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable

from . import config

SENTINEL_TEMPLATE = "[[E{n}]]"
SENTINEL_RE = re.compile(r"\[\[E(\d+)\]\]")
# Debris left when a translator mangles a sentinel: "[ [E4] ]", "[[E4]", "[[ E4 ]]".
SENTINEL_DEBRIS_RE = re.compile(r"\[\s*\[?\s*E\s*\d+\s*\]?\s*\]?|\[\[|\]\]")

VERSION = "1.2"


# ---------------------------------------------------------------------------
# Patterns, highest priority first
# ---------------------------------------------------------------------------

MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December|"
    "Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
)
DAYS = "Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday"
TZ = "EDT|EST|CDT|CST|MDT|MST|PDT|PST|AKDT|AKST|HST|UTC|GMT|Z"
UNITS = (
    "feet|foot|ft|inches|inch|in|miles|mile|mi|mph|kt|knots|km|kph|meters|metres|m|"
    "degrees|percent|hours|hour|hrs|hr|minutes|minute|mins|min|seconds|second|"
    "cfs|acres|pounds|lbs"
)

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("url", re.compile(r"\bhttps?://\S+|\bwww\.[\w.-]+\.\w{2,}(?:/\S*)?", re.I)),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    # Bare government and nonprofit domains: "DisasterAssistance.gov",
    # "IdentityTheft.gov". A reader who cannot follow the translation still
    # needs to be able to type the address exactly.
    ("domain", re.compile(r"\b[A-Za-z][\w-]*(?:\.[\w-]+)*\.(?:gov|org|mil)\b")),
    # FEMA declaration identifiers. FEMA's own appeal instructions say to put
    # the disaster number on every page, so it must not drift in translation.
    ("declaration", re.compile(r"\b(?:DR|EM|FM)-\d{3,4}(?:-[A-Z]{2})?\b")),
    # Emergency short codes. Without this, "9-1-1" locks as three separate
    # digits and the hyphens travel through the translator unprotected.
    ("phone_short", re.compile(r"\b(?:9-1-1|911|988|2-1-1|211)\b")),
    # NWS dictates phone numbers for text-to-speech as spoken digit groups:
    # "calling toll free at 1...8 6 6...2 1 5...4 3 2 4". A generic phone regex
    # misses this entirely and the digits then travel through the model
    # unprotected, which is exactly how a reporting hotline turns into a wrong
    # number. Matched before the ordinary form so the longer span wins.
    (
        "phone_spoken",
        re.compile(r"\b\d(?:\s\d)*\s*\.{2,}\s*\d(?:\s\d)*(?:\s*\.{2,}\s*\d(?:\s\d)*)+"),
    ),
    ("phone", re.compile(r"\b(?:\+?1[-. ])?(?:\(\d{3}\)\s*|\d{3}[-.])\d{3}[-.]\d{4}\b")),
    (
        "address",
        re.compile(
            # Trailing period is part of the entity only after an abbreviated
            # street type ("110 Main St."), never after a spelled-out one,
            # where it is the sentence's own full stop.
            r"\b\d{1,6}\s+(?:[NSEW]\.?\s+)?[A-Z][\w'-]*(?:\s+[A-Z][\w'-]*){0,3}\s+"
            r"(?:(?:Street|Avenue|Road|Boulevard|Drive|Lane|Court|Circle|Parkway|"
            r"Highway|Turnpike|Pike|Way|Place|Terrace|Trail)\b"
            r"|(?:St|Ave|Rd|Blvd|Dr|Ln|Ct|Cir|Pkwy|Hwy|Pl|Tpke)\b\.?)",
        ),
    ),
    (
        "road",
        re.compile(
            r"\b(?:"
            r"I[- ]\d{1,3}(?:[- ]?[NSEW])?"
            r"|Interstate\s+\d{1,3}"
            r"|U\.?S\.?[- ]?(?:Route\s+|Highway\s+|Hwy\s+)?\d{1,3}"
            r"|VA[- ]\d{1,4}"
            r"|(?:State\s+)?(?:Route|Rt\.?|Rte\.?|Highway|Hwy)\s+\d{1,4}"
            r"|Exit\s+\d{1,3}[A-Z]?"
            r"|Mile\s+Marker\s+\d{1,3}"
            r"|Business\s+\d{1,3}"
            r")\b",
            re.I,
        ),
    ),
    (
        "time",
        re.compile(
            r"\b(?:"
            rf"\d{{1,2}}:\d{{2}}\s*(?:[AP]\.?M\.?)?\s*(?:{TZ})?"
            rf"|\d{{3,4}}\s*(?:[AP]\.?M\.?)\s*(?:{TZ})?"
            rf"|\d{{1,2}}\s*(?:[AP]\.?M\.?)\s*(?:{TZ})?"
            rf"|(?:{MONTHS})\.?\s+\d{{1,2}}(?:,\s*\d{{4}})?"
            rf"|(?:{DAYS})(?:\s+(?:morning|afternoon|evening|night))?"
            rf"|\d{{4}}-\d{{2}}-\d{{2}}T[\d:]+(?:[+-]\d{{2}}:\d{{2}}|Z)?"
            rf"|\d{{1,2}}/\d{{1,2}}/\d{{2,4}}"
            rf"|midnight|noon"
            r")\b",
            re.I,
        ),
    ),
    ("timezone", re.compile(rf"\b(?:{TZ})\b")),
    (
        "waterway",
        re.compile(
            r"\b(?:[A-Z][\w'-]+(?:\s+[A-Z][\w'-]+){0,3}\s+)"
            r"(?:River|Creek|Run|Branch|Fork|Bay|Lake|Reservoir|Dam|Inlet|Sound|Brook|Swamp)\b",
        ),
    ),
    (
        "measurement",
        re.compile(rf"\b\d+(?:\.\d+)?\s*(?:{UNITS})\b\.?", re.I),
    ),
    ("ordinal", re.compile(r"\b\d+(?:st|nd|rd|th)\b", re.I)),
    ("number", re.compile(r"\b\d+(?:[.,]\d+)*\b")),
]

PRIORITY = {kind: i for i, (kind, _) in enumerate(PATTERNS)}
PRIORITY["place"] = PRIORITY["waterway"] + 1  # gazetteer hits outrank measurements

MEASUREMENT_SPLIT = re.compile(rf"^(\d+(?:\.\d+)?)\s*({UNITS})\b\.?$", re.I)

# Curated unit words. Hand-written, not model output; a wrong unit here is a
# safety bug, so the table stays small and every entry is a common noun.
UNIT_WORDS: dict[str, dict[str, str]] = {
    "es": {
        "feet": "pies", "foot": "pie", "ft": "pies",
        "inches": "pulgadas", "inch": "pulgada",
        "miles": "millas", "mile": "milla", "mph": "millas por hora",
        "hours": "horas", "hour": "hora", "minutes": "minutos", "minute": "minuto",
        "percent": "por ciento", "degrees": "grados",
    },
    "tl": {
        "feet": "talampakan", "foot": "talampakan", "ft": "talampakan",
        "inches": "pulgada", "inch": "pulgada",
        "miles": "milya", "mile": "milya", "mph": "milya kada oras",
        "hours": "oras", "hour": "oras", "minutes": "minuto", "minute": "minuto",
        "percent": "porsyento",
    },
    "ar": {
        "feet": "قدم", "foot": "قدم", "ft": "قدم",
        "inches": "بوصة", "inch": "بوصة",
        "miles": "ميل", "mile": "ميل",
        "hours": "ساعات", "hour": "ساعة",
        "minutes": "دقائق", "minute": "دقيقة",
    },
    "prs": {
        "feet": "فوت", "foot": "فوت", "ft": "فوت",
        "inches": "انچ", "inch": "انچ",
        "miles": "مایل", "mile": "مایل",
        "hours": "ساعت", "hour": "ساعت",
        "minutes": "دقیقه", "minute": "دقیقه",
    },
}


@dataclass
class Entity:
    id: str
    kind: str
    text: str
    start: int
    end: int
    numeric_core: str | None = None
    unit: str | None = None

    @property
    def sentinel(self) -> str:
        return SENTINEL_TEMPLATE.format(n=self.id[1:])

    def render(self, unit_lang: str | None = None) -> str:
        """Text to substitute back in. Numerals never change."""
        if unit_lang and self.numeric_core and self.unit:
            table = UNIT_WORDS.get(unit_lang, {})
            word = table.get(self.unit.lower())
            if word:
                return f"{self.numeric_core} {word}"
        return self.text

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LockResult:
    masked: str
    entities: list[Entity]
    original: str

    @property
    def by_sentinel(self) -> dict[str, Entity]:
        return {e.sentinel: e for e in self.entities}


@dataclass
class IntegrityReport:
    passed: bool
    missing: list[str] = field(default_factory=list)
    duplicated: list[str] = field(default_factory=list)
    unexpected: list[str] = field(default_factory=list)
    debris: list[str] = field(default_factory=list)
    numeric_dropped: list[str] = field(default_factory=list)

    def reason(self) -> str:
        bits = []
        if self.missing:
            bits.append(f"missing {self.missing}")
        if self.duplicated:
            bits.append(f"duplicated {self.duplicated}")
        if self.unexpected:
            bits.append(f"unexpected {self.unexpected}")
        if self.debris:
            bits.append(f"mangled sentinel debris {self.debris[:3]}")
        if self.numeric_dropped:
            bits.append(f"numeral missing after restore {self.numeric_dropped}")
        return "; ".join(bits) or "ok"

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Gazetteer
# ---------------------------------------------------------------------------


class Gazetteer:
    """Place names to lock. Built from the alert's own areaDesc plus a Virginia
    place list (see scripts/build_gazetteer.py)."""

    def __init__(self, names: Iterable[str] | None = None) -> None:
        self._names: set[str] = set()
        self._pattern: re.Pattern[str] | None = None
        if names:
            self.add_many(names)

    @classmethod
    def load(cls, path: Path | None = None) -> "Gazetteer":
        path = path or config.GAZETTEER_PATH
        if not path.exists():
            return cls()
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        return cls(data.get("names", []))

    def add_many(self, names: Iterable[str]) -> None:
        for n in names:
            n = (n or "").strip()
            # One-word lowercase fragments make false positives; require either
            # a capital or a multi-word name.
            if len(n) < 3:
                continue
            if not (n[0].isupper() or " " in n):
                continue
            self._names.add(n)
        self._pattern = None

    def add_from_area_desc(self, area_desc: str) -> None:
        """The alert names its own places. Highest-precision source available."""
        parts = re.split(r"[;,]", area_desc or "")
        cleaned = []
        for p in parts:
            p = re.sub(r"\b(?:VA|Virginia|County|City|Counties)\b\.?", "", p).strip()
            if p:
                cleaned.append(p)
        self.add_many(cleaned)

    @property
    def pattern(self) -> re.Pattern[str] | None:
        if self._pattern is None and self._names:
            ordered = sorted(self._names, key=len, reverse=True)
            self._pattern = re.compile(
                r"(?<![\w'])(" + "|".join(re.escape(n) for n in ordered) + r")(?![\w'])"
            )
        return self._pattern

    def __len__(self) -> int:
        return len(self._names)


# ---------------------------------------------------------------------------
# Lock / unlock
# ---------------------------------------------------------------------------


def _candidates(text: str, gazetteer: Gazetteer | None) -> list[tuple[int, int, str]]:
    found: list[tuple[int, int, str]] = []
    for kind, pattern in PATTERNS:
        for m in pattern.finditer(text):
            if m.group(0).strip():
                found.append((m.start(), m.end(), kind))
    if gazetteer is not None and gazetteer.pattern is not None:
        for m in gazetteer.pattern.finditer(text):
            found.append((m.start(), m.end(), "place"))
    return found


def _resolve(spans: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
    """Greedy non-overlapping selection: longer wins, then higher priority."""
    spans.sort(key=lambda s: (-(s[1] - s[0]), PRIORITY.get(s[2], 99), s[0]))
    taken: list[tuple[int, int, str]] = []
    for start, end, kind in spans:
        if any(not (end <= ts or start >= te) for ts, te, _ in taken):
            continue
        taken.append((start, end, kind))
    taken.sort(key=lambda s: s[0])
    return taken


def lock(text: str, gazetteer: Gazetteer | None = None) -> LockResult:
    """Replace must-survive spans with sentinels. Pure and deterministic."""
    if not text:
        return LockResult(masked="", entities=[], original=text or "")

    spans = _resolve(_candidates(text, gazetteer))

    entities: list[Entity] = []
    out: list[str] = []
    cursor = 0
    for i, (start, end, kind) in enumerate(spans, start=1):
        surface = text[start:end]
        ent = Entity(id=f"E{i}", kind=kind, text=surface, start=start, end=end)
        if kind == "measurement":
            m = MEASUREMENT_SPLIT.match(surface.strip())
            if m:
                ent.numeric_core, ent.unit = m.group(1), m.group(2)
        entities.append(ent)
        out.append(text[cursor:start])
        out.append(ent.sentinel)
        cursor = end
    out.append(text[cursor:])
    return LockResult(masked="".join(out), entities=entities, original=text)


def check_integrity(candidate: str, entities: list[Entity]) -> IntegrityReport:
    """Stage 3 check 1: every sentinel restored exactly once, unmodified.

    Runs on the *masked* candidate, before restoration - that is the only point
    at which a dropped or duplicated sentinel is still visible.
    """
    expected = {e.sentinel for e in entities}
    found = SENTINEL_RE.findall(candidate)
    found_sentinels = [SENTINEL_TEMPLATE.format(n=n) for n in found]
    counts: dict[str, int] = {}
    for s in found_sentinels:
        counts[s] = counts.get(s, 0) + 1

    missing = sorted(expected - set(counts))
    duplicated = sorted(s for s, c in counts.items() if c > 1)
    unexpected = sorted(set(counts) - expected)

    stripped = SENTINEL_RE.sub("", candidate)
    debris = [d for d in SENTINEL_DEBRIS_RE.findall(stripped) if d.strip()]

    return IntegrityReport(
        passed=not (missing or duplicated or unexpected or debris),
        missing=missing,
        duplicated=duplicated,
        unexpected=unexpected,
        debris=debris,
    )


def unlock(
    candidate: str, entities: list[Entity], unit_lang: str | None = None
) -> tuple[str, IntegrityReport]:
    """Restore entities and re-check that every numeral survived the round trip."""
    report = check_integrity(candidate, entities)
    by_sentinel = {e.sentinel: e for e in entities}

    def repl(m: re.Match[str]) -> str:
        ent = by_sentinel.get(m.group(0))
        return ent.render(unit_lang) if ent else m.group(0)

    restored = SENTINEL_RE.sub(repl, candidate)

    # Belt and braces: the numeral itself must be present in the final string.
    dropped = [
        e.id
        for e in entities
        if e.numeric_core and e.numeric_core not in restored
    ]
    if dropped:
        report.numeric_dropped = dropped
        report.passed = False
    return restored, report


def locked_entities_summary(entities: list[Entity]) -> dict[str, int]:
    out: dict[str, int] = {}
    for e in entities:
        out[e.kind] = out.get(e.kind, 0) + 1
    return out
