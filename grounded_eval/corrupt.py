"""Corruption injection: how you get honest numbers on a subjective task.

Brief section 7. Take real verified output from the real pipeline and damage it
in five specific ways, then measure whether the verifier notices. The ground
truth is not invented and the data is not generated - only the damage is, and
the damage is exactly the set of failures that matter operationally.

    class                     what it simulates
    drop_negation             "do not cross" rendered as "cross"
    alter_number              3 feet reported as 8 feet
    swap_road                 US-58 rendered as US-85
    hallucinate_instruction   an action the source never issued
    drop_instruction          a required action silently missing

INJECTION POINT, and this is the part that decides whether the numbers mean
anything. Corruption is applied to the *masked* candidate, which is where a
real transformation failure would occur - after the lock, before restoration.
At that point numbers and roads are sentinels, so corrupting one means
tampering with a sentinel, and entity integrity sees it. That is not the
harness being kind to itself; it is the measurement showing what the lock buys.

To quantify that, `--ablate-entity-lock` reruns the same corruptions with
locking disabled, so the report can state what the remaining three checks catch
without it. The gap between those two columns is the argument for the design.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Callable

from grounded import entities as ent

CLASSES = (
    "drop_negation",
    "alter_number",
    "swap_road",
    "hallucinate_instruction",
    "drop_instruction",
)

NEGATION_PATTERNS = [
    (re.compile(r"\bdo not\s+", re.I), ""),
    (re.compile(r"\bdon't\s+", re.I), ""),
    (re.compile(r"\bnever\s+", re.I), ""),
    (re.compile(r"\bcannot\s+", re.I), "can "),
    (re.compile(r"\bavoid\s+", re.I), "use "),
    (re.compile(r"\bno longer\s+", re.I), "still "),
]

# Instructions that sound entirely plausible in a flood or tornado product and
# appear in none of them. This is the failure mode a fluent model produces.
HALLUCINATIONS = [
    "Shelters are open at the local high school.",
    "Emergency crews are on the way to your street.",
    "Boil all tap water before drinking it.",
    "Take Route 11 south to reach the evacuation point.",
    "Call 911 now to be added to the rescue list.",
    "The mandatory evacuation order covers your address.",
]

ROAD_DIGITS = re.compile(r"(\d+)")


@dataclass
class Corruption:
    cls: str
    segment_id: str
    before: str
    after: str
    applied: bool
    note: str = ""


def _swap_digits(value: str) -> str:
    """Change a number to a different, still-plausible number."""

    def repl(m: re.Match[str]) -> str:
        digits = m.group(1)
        try:
            n = int(digits)
        except ValueError:
            return digits
        new = n + 5 if n < 50 else max(1, n // 2)
        if new == n:
            new = n + 1
        return str(new)

    return ROAD_DIGITS.sub(repl, value, count=1)


# ---------------------------------------------------------------------------
# Corruptions on masked text (the real injection point)
# ---------------------------------------------------------------------------


def _sentinel_of(entity: dict) -> str:
    return ent.SENTINEL_TEMPLATE.format(n=str(entity["id"]).lstrip("Ee"))


def corrupt_masked(cls: str, text: str, locked: list[dict],
                   rng: random.Random) -> tuple[str, bool, str]:
    """Return (corrupted_text, applied, note). `locked` holds entity dicts as
    they appear in a render's segment payload."""
    if cls == "drop_negation":
        for pattern, repl in NEGATION_PATTERNS:
            if pattern.search(text):
                return pattern.sub(repl, text, count=1), True, "negation removed"
        return text, False, "no negation present"

    if cls in ("alter_number", "swap_road"):
        wanted = (
            ("measurement", "number", "ordinal")
            if cls == "alter_number"
            else ("road", "address")
        )
        targets = [e for e in locked if e.get("kind") in wanted]
        if not targets:
            return text, False, f"no {cls.split('_')[1]} entity locked"
        victim = rng.choice(targets)
        sentinel = _sentinel_of(victim)
        if sentinel not in text:
            return text, False, f"{victim['id']} sentinel absent from candidate"
        # Replace the sentinel with an altered literal: exactly what an unlocked
        # pipeline would emit, and a sentinel the integrity check now misses.
        return (
            text.replace(sentinel, _swap_digits(victim["text"]), 1),
            True,
            f"{victim['id']} {victim['text']!r} -> altered literal",
        )

    if cls == "hallucinate_instruction":
        return text.rstrip() + " " + rng.choice(HALLUCINATIONS), True, "appended unsourced action"

    if cls == "drop_instruction":
        return "", True, "segment emptied"

    raise ValueError(f"unknown corruption class: {cls}")


def corrupt_plain(cls: str, text: str, rng: random.Random) -> tuple[str, bool, str]:
    """Same five classes against unmasked text, for the ablation run."""
    if cls == "drop_negation":
        for pattern, repl in NEGATION_PATTERNS:
            if pattern.search(text):
                return pattern.sub(repl, text, count=1), True, "negation removed"
        return text, False, "no negation present"

    if cls in ("alter_number", "swap_road"):
        if cls == "swap_road":
            m = re.search(r"\b(?:I|US|VA|Route|Exit|Highway)[- ]?\d{1,4}\b", text, re.I)
        else:
            m = re.search(r"\b\d+(?:\.\d+)?\b", text)
        if not m:
            return text, False, "no target present"
        return (
            text[: m.start()] + _swap_digits(m.group(0)) + text[m.end() :],
            True,
            f"{m.group(0)!r} altered",
        )

    if cls == "hallucinate_instruction":
        return text.rstrip() + " " + rng.choice(HALLUCINATIONS), True, "appended unsourced action"

    if cls == "drop_instruction":
        return "", True, "segment emptied"

    raise ValueError(f"unknown corruption class: {cls}")


# ---------------------------------------------------------------------------
# Hook factory used with transform.transform_alert(corrupt_fn=...)
# ---------------------------------------------------------------------------


def make_corruptor(cls: str, target_segment_id: str, locked_by_segment: dict[str, list],
                   seed: int = 0, masked: bool = True) -> tuple[Callable, dict]:
    """Build a corrupt_fn that damages exactly one segment.

    One segment at a time keeps attribution clean: whatever the verifier says
    about that segment is caused by that corruption and nothing else.
    """
    rng = random.Random(seed)
    record: dict = {"cls": cls, "segment_id": target_segment_id, "applied": False, "note": ""}

    def fn(segment_id: str, text: str):
        if segment_id != target_segment_id:
            return None
        locked = locked_by_segment.get(segment_id, [])
        if masked:
            out, applied, note = corrupt_masked(cls, text, locked, rng)
        else:
            out, applied, note = corrupt_plain(cls, text, rng)
        record["applied"] = applied
        record["note"] = note
        record["before"] = text
        record["after"] = out
        return out if applied else None

    return fn, record


# Eligibility must work in both arms of the experiment. In the ablation arm
# there are no locked entities to inspect, so fall back to the source text -
# otherwise the ablation silently finds nothing to corrupt and the comparison
# it exists to support never happens.
PLAIN_NUMBER = re.compile(r"\b\d+(?:\.\d+)?\b")
PLAIN_ROAD = re.compile(r"\b(?:I|US|VA|Route|Exit|Highway|Hwy)[- ]?\d{1,4}\b", re.I)


def eligible_segments(cls: str, segments: list[dict]) -> list[str]:
    """Which segments this corruption class can meaningfully damage."""
    out = []
    for seg in segments:
        kinds = {e.get("kind") for e in seg.get("entities", [])}
        text = seg.get("source_text", "")
        if cls == "drop_negation":
            if any(p.search(text) for p, _ in NEGATION_PATTERNS):
                out.append(seg["id"])
        elif cls == "alter_number":
            if kinds & {"measurement", "number", "ordinal"} or (
                not kinds and PLAIN_NUMBER.search(text)
            ):
                out.append(seg["id"])
        elif cls == "swap_road":
            if kinds & {"road", "address"} or (not kinds and PLAIN_ROAD.search(text)):
                out.append(seg["id"])
        elif cls in ("hallucinate_instruction", "drop_instruction"):
            if seg.get("role") == "instruction":
                out.append(seg["id"])
    return out
