"""When to stop navigating and hand the person to a human.

The challenge asks for escalation of "sensitive, ambiguous, urgent, or
high-impact cases to a human representative". This module is that, built so
that the part which must never fail is the part with no model in it.

    INVARIANT - the floor. Deterministic rules decide the minimum escalation.
    A model classifier (Azure OpenAI, when configured) may ADD triggers. There
    is no code path by which a model lowers the level or removes a trigger the
    rules raised. `merge()` is a union and `level` is a max, and the tests pin
    both. A model that misses "trapped in the attic" cannot un-escalate it.

Every channel a person is sent to is a verbatim quote from a cached
authoritative page (data/programs.json -> "channels"), so the number shown is
the number the agency publishes, not one remembered by this code.

Errs towards escalating. A false positive costs a person one extra sentence
pointing at a phone number. A false negative is the failure this exists for.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict

from . import sources

LEVELS = ["none", "ambiguous", "high_impact", "fraud", "sensitive", "urgent"]
RANK = {name: i for i, name in enumerate(LEVELS)}


@dataclass
class Trigger:
    id: str
    level: str
    reason: str
    channels: list[str]
    matched: str | None = None
    source: str = "rule"  # "rule" | "flag" | "model" | "system"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Escalation:
    triggers: list[Trigger] = field(default_factory=list)

    @property
    def level(self) -> str:
        if not self.triggers:
            return "none"
        return max((t.level for t in self.triggers), key=lambda lv: RANK[lv])

    @property
    def human_first(self) -> bool:
        """Show the handoff above everything else, before any program list."""
        return RANK[self.level] >= RANK["sensitive"]

    def channel_ids(self) -> list[str]:
        seen: list[str] = []
        for t in sorted(self.triggers, key=lambda t: -RANK[t.level]):
            for c in t.channels:
                if c not in seen:
                    seen.append(c)
        return seen

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "human_first": self.human_first,
            "triggers": [t.to_dict() for t in self.triggers],
            "channels": [resolve_channel(c) for c in self.channel_ids()],
        }


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

# (id, level, channels, reason, English patterns)
_RULES: list[tuple[str, str, list[str], str, list[str]]] = [
    ("danger_now", "urgent", ["emergency_911"],
     "Someone may be in danger right now. Call 911 before anything else.",
     [r"\btrapped\b", r"\bstuck (?:in|on) (?:the |my |a )?(?:roof|attic|car|water|house)",
      r"can'?t get out", r"cannot get out", r"water (?:is )?rising", r"\bdrown",
      r"\bfire\b", r"\bsmoke\b", r"gas leak", r"smell(?:s|ing)? gas", r"\binjur",
      r"\bbleeding\b", r"\bunconscious\b", r"not breathing", r"can'?t breathe",
      r"cannot breathe", r"chest pain", r"heart attack", r"\bstroke\b", r"\bseizure",
      r"\bambulance\b", r"\bdying\b",
      r"(?:no|out of|need|lost (?:my|his|her)) (?:oxygen|insulin|dialysis|medication|medicine)",
      r"missing (?:child|kid|person|family|son|daughter|mother|father)"]),
    ("self_harm", "urgent", ["crisis_988", "distress_line"],
     "You deserve support right now. Trained counselors are available at any hour.",
     [r"suicid", r"kill myself", r"end (?:my|it all)", r"want to die", r"don'?t want to live",
      r"hurt(?:ing)? myself", r"self[- ]harm", r"no reason to live", r"better off dead"]),
    ("abuse", "sensitive", ["emergency_911", "distress_line", "legal_aid"],
     "If you are not safe where you are, a person can help you plan next steps.",
     [r"\babus(?:e|ive|ing)\b", r"hits? me\b", r"hitting me", r"beats? me", r"beating me",
      r"\bviolen(?:t|ce)\b", r"threaten(?:s|ed|ing)? (?:me|to)",
      r"afraid of my (?:partner|husband|wife|boyfriend|girlfriend|ex)", r"\bdomestic\b"]),
    ("immigration", "sensitive", ["immigration_expert", "legal_aid"],
     "Questions about immigration status should go to a person, not this tool. "
     "Some help is available regardless of status - see below.",
     [r"immigra", r"undocumented", r"\bcitizen", r"green card", r"\bvisa\b", r"asylum",
      r"\brefugee", r"deport", r"\bICE\b", r"\bDACA\b", r"\bTPS\b", r"not a (?:us |u\.s\. )?citizen"]),
    ("identity_theft", "sensitive", ["fema_helpline", "identity_theft"],
     "If FEMA contacted you about an application you did not make, your identity may have been used.",
     [r"(?:did ?n[o']t|never) appl(?:y|ied)", r"someone (?:else )?applied",
      r"identity theft", r"stole(?:n)? (?:my )?identity",
      r"using my (?:name|social|ssn|information|identity)"]),
    ("fraud", "fraud", ["fraud_report", "fema_helpline"],
     "FEMA and other federal agencies never charge to apply or to help you apply.",
     [r"(?:asked|asking|asks|wants?|wanted|demand(?:s|ed)?) (?:me )?(?:for )?(?:money|a fee|fees|payment|cash|a deposit|gift cards?|a wire|my bank|bank info|my account|my registration|my social|my ssn)",
      r"(?:charged?|charging) (?:me )?(?:a fee|to apply|to register|money)",
      r"pay (?:a fee |money )?to (?:apply|register|get)", r"guaranteed? (?:a )?grant",
      r"\bscam", r"fake (?:inspector|fema)", r"suspicious (?:call|text|email|person|man|woman|message)",
      r"(?:all|full|everything) (?:up ?front|in advance)", r"\bgift cards?\b"]),
    ("high_impact", "high_impact", ["fema_helpline", "legal_aid"],
     "Decisions like this have deadlines. A person can walk you through your options.",
     [r"\bdenied\b", r"\bdenial\b", r"\bineligible\b", r"not eligible", r"\brejected\b",
      r"\bappeal", r"recoup", r"debt letter", r"potential debt", r"pay (?:it |the money )?back",
      r"\bevict", r"kick(?:ing|ed)? (?:me|us) out", r"\bforeclos"]),
]

# A deliberately small floor for the most urgent phrases in the demo languages.
# Not native-speaker reviewed, and not a substitute for translating first: with
# Azure configured the text is translated to English and the English rules run
# as well. This exists so the offline path does not go silent on "atrapado".
_MULTILINGUAL_URGENT: dict[str, list[str]] = {
    "danger_now": [r"atrapad", r"herid", r"no puedo respirar", r"incendio", r"me ahogo",
                   r"nakulong", r"sugatan", r"hindi makahinga", r"sunog",
                   "محاصر", "مصاب", "حريق",
                   "گیر افتاده", "زخمی", "آتش"],
    "self_harm": [r"suicid", r"me quiero morir", r"magpakamatay",
                  "انتحار", "خودکشی"],
}

_COMPILED = [
    (rid, level, channels, reason, [re.compile(p, re.I) for p in pats])
    for rid, level, channels, reason, pats in _RULES
]
_COMPILED_ML = {rid: [re.compile(p, re.I) for p in pats] for rid, pats in _MULTILINGUAL_URGENT.items()}
_RULE_META = {rid: (level, channels, reason) for rid, level, channels, reason, _ in _RULES}


def rule_triggers(text: str | None) -> list[Trigger]:
    """The floor. Deterministic, offline, and run on redacted text only."""
    if not text:
        return []
    found: list[Trigger] = []
    for rid, level, channels, reason, patterns in _COMPILED:
        for p in patterns:
            m = p.search(text)
            if m:
                found.append(Trigger(rid, level, reason, channels, m.group(0), "rule"))
                break
    for rid, patterns in _COMPILED_ML.items():
        if any(t.id == rid for t in found):
            continue
        for p in patterns:
            m = p.search(text)
            if m:
                level, channels, reason = _RULE_META[rid]
                found.append(Trigger(rid, level, reason, channels, m.group(0), "rule"))
                break
    return found


def flag_triggers(danger_now: bool = False, needs: list[str] | None = None) -> list[Trigger]:
    """Structured answers from the form - more reliable than parsing prose."""
    out: list[Trigger] = []
    if danger_now:
        level, channels, reason = _RULE_META["danger_now"]
        out.append(Trigger("danger_now", level, reason, channels, None, "flag"))
    needs = needs or []
    if "scam_concern" in needs:
        level, channels, reason = _RULE_META["fraud"]
        out.append(Trigger("fraud", level, reason, channels, None, "flag"))
    if "appeal" in needs:
        level, channels, reason = _RULE_META["high_impact"]
        out.append(Trigger("high_impact", level, reason, channels, None, "flag"))
    if "emotional_distress" in needs:
        out.append(Trigger("emotional_distress", "high_impact",
                           "Talking to someone can help. Crisis counselors answer in many languages.",
                           ["distress_line"], None, "flag"))
    return out


def system_trigger(tid: str, reason: str, channels: list[str] | None = None) -> Trigger:
    """Raised by the navigator itself: ambiguous location, abstained segments,
    damage reported where no declaration exists."""
    return Trigger(tid, "ambiguous", reason, channels or ["fema_helpline"], None, "system")


def merge(*groups: list[Trigger]) -> Escalation:
    """Union. Never drops a trigger, and since `level` is a max over triggers,
    adding a group can only hold or raise the level - never lower it."""
    by_id: dict[str, Trigger] = {}
    for group in groups:
        for t in group or []:
            existing = by_id.get(t.id)
            if existing is None or RANK[t.level] > RANK[existing.level]:
                by_id[t.id] = t
    return Escalation(triggers=list(by_id.values()))


# ---------------------------------------------------------------------------
# Channels, resolved to citations
# ---------------------------------------------------------------------------

_CHANNELS: dict | None = None


def _channels() -> dict:
    global _CHANNELS
    if _CHANNELS is None:
        with sources.PROGRAMS_PATH.open(encoding="utf-8") as fh:
            _CHANNELS = json.load(fh).get("channels", {})
    return _CHANNELS


def resolve_channel(channel_id: str) -> dict:
    """A channel is shown only with its citation. If the quote no longer
    appears in the cached page, the channel is marked unverified rather than
    shown as if it were confirmed."""
    spec = _channels().get(channel_id)
    if not spec:
        return {"id": channel_id, "label": channel_id, "verified": False,
                "reason": "channel not in catalog"}
    cite = sources.locate(spec["doc"], spec["quote"])
    return {
        "id": channel_id,
        "label": spec["label"],
        "verified": cite is not None,
        "citation": cite.to_dict() if cite else None,
    }
