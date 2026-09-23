"""Turning the CAP `instruction` field into numbered, cited steps.

Brief section 3.3, INVARIANT: the `instruction` field is the only authoritative
source of actions. Never generate an action absent from it. When it is empty -
and it often is - show the description and say plainly that the source carried
no instructions. Do not infer. Do not helpfully suggest.

Every step therefore carries `source_span`, a pair of character offsets into
the *raw* instruction string. That is what makes a step checkable: a reader can
slice the original field and see exactly what the step came from.

NWS hard-wraps instruction text at around 70 columns, mid-sentence. Unwrapping
is required before sentences can be found at all, so the unwrap keeps an index
map back to the raw string and the offsets stay true.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict

from .providers.local_providers import split_sentences

# Verbs that open an NWS protective-action sentence. Used only to *label* a
# sentence as an action; nothing is ever dropped for failing to match.
IMPERATIVE_OPENERS = {
    "avoid", "be", "bring", "call", "check", "climb", "close", "continue", "do",
    "dial", "drive", "evacuate", "expect", "follow", "get", "give", "go", "head",
    "heed", "keep", "leave", "listen", "look", "monitor", "move", "never", "obey",
    "prepare", "protect", "remain", "remember", "report", "return", "seek", "send",
    "shelter", "stay", "stop", "take", "tell", "turn", "use", "wait", "watch",
    "if", "when", "once",
}
MODAL_ACTION = re.compile(
    r"\b(?:you should|you must|should|must|need to|do not|don't|never)\b", re.I
)


@dataclass
class Step:
    index: int
    text: str
    source_span: tuple[int, int]
    kind: str  # "action" | "context"
    required: bool

    def to_dict(self) -> dict:
        d = asdict(self)
        d["source_span"] = list(self.source_span)
        return d


def unwrap(raw: str) -> tuple[str, list[int]]:
    """Join NWS hard-wrapped lines, keeping an offset map into `raw`.

    Returns (unwrapped_text, index_map) where index_map[i] is the offset in
    `raw` of unwrapped_text[i].
    """
    out_chars: list[str] = []
    index_map: list[int] = []
    i = 0
    n = len(raw)
    while i < n:
        ch = raw[i]
        if ch == "\r":
            i += 1
            continue
        if ch == "\n":
            # A blank line is a real paragraph break; a lone newline is a wrap.
            j = i
            newlines = 0
            while j < n and raw[j] in "\r\n":
                if raw[j] == "\n":
                    newlines += 1
                j += 1
            if newlines >= 2:
                out_chars.append("\n")
                index_map.append(i)
                out_chars.append("\n")
                index_map.append(i)
            else:
                if out_chars and out_chars[-1] not in " \n":
                    out_chars.append(" ")
                    index_map.append(i)
            i = j
            continue
        out_chars.append(ch)
        index_map.append(i)
        i += 1
    return "".join(out_chars), index_map


def _span_in_raw(unwrapped_start: int, unwrapped_end: int, index_map: list[int],
                 raw_len: int) -> tuple[int, int]:
    if not index_map:
        return (0, 0)
    start = index_map[min(unwrapped_start, len(index_map) - 1)]
    last = min(max(unwrapped_end - 1, 0), len(index_map) - 1)
    end = min(index_map[last] + 1, raw_len)
    return (start, max(end, start))


def classify(sentence: str) -> str:
    """action vs context. Errs towards `action`, which is the safe direction:
    an action mislabelled as context would relax the coverage check."""
    s = sentence.strip()
    if not s:
        return "context"
    if MODAL_ACTION.search(s):
        return "action"
    first = re.sub(r"^[^A-Za-z]+", "", s).split(" ", 1)[0].lower().strip(",.!?")
    if first in IMPERATIVE_OPENERS:
        return "action"
    if s.isupper() and len(s.split()) <= 12:
        return "action"  # "TAKE COVER NOW!"
    return "context"


def parse_instruction(raw: str | None) -> list[Step]:
    """Split `instruction` into cited steps. Empty input yields an empty list -
    never a default action."""
    if not raw or not raw.strip():
        return []
    text, index_map = unwrap(raw)
    steps: list[Step] = []
    cursor = 0
    idx = 0
    for para in text.split("\n\n"):
        if not para.strip():
            cursor += len(para) + 2
            continue
        for sentence in split_sentences(para):
            found = text.find(sentence, cursor)
            if found < 0:
                found = text.find(sentence)
            if found < 0:
                continue
            cursor = found + len(sentence)
            kind = classify(sentence)
            idx += 1
            steps.append(
                Step(
                    index=idx,
                    text=sentence.strip(),
                    source_span=_span_in_raw(found, cursor, index_map, len(raw)),
                    kind=kind,
                    required=(kind == "action"),
                )
            )
        cursor = max(cursor, text.find(para) + len(para))
    return steps


def verify_spans(raw: str, steps: list[Step]) -> list[tuple[int, bool]]:
    """Every step's span must actually slice back to (close to) its own text.

    Cheap, and it catches offset drift immediately - which matters, because an
    offset that silently points at the wrong sentence turns the citation from
    evidence into decoration.
    """
    results = []
    for step in steps:
        start, end = step.source_span
        sliced = re.sub(r"\s+", " ", raw[start:end]).strip()
        wanted = re.sub(r"\s+", " ", step.text).strip()
        results.append((step.index, sliced == wanted))
    return results


def describe_coverage(raw: str | None) -> dict:
    """Reported as a finding, not a score (brief section 7)."""
    steps = parse_instruction(raw)
    return {
        "has_instruction": bool(raw and raw.strip()),
        "steps": len(steps),
        "actions": sum(1 for s in steps if s.kind == "action"),
        "context": sum(1 for s in steps if s.kind == "context"),
    }
