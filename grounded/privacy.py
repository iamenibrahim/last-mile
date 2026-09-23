"""Data minimisation for free text a survivor types in.

The navigator needs two things to help: which county, and what happened. It
does not need a name, a Social Security number, a FEMA registration number, a
bank account or a date of birth, and it must not ask for them - FEMA's own
fraud guidance says a real inspector will "Never ask for your nine-digit
registration number", and a tool that trains people to type identifiers into a
text box is training them for the scam.

So identifiers are removed *before* anything else sees the text: before need
detection, before escalation rules, before any Azure call, before logging. The
redacted text lives only for the length of the request and is never stored.
What is stored for a render is the county FIPS code and the need codes.

Redaction errs towards removing too much. A false positive costs a word of
context; a false negative puts an SSN in a model prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


# Order matters: longer and more specific patterns first, so a card number is
# not half-eaten by the nine-digit rule.
RULES: list[tuple[str, re.Pattern[str]]] = [
    ("card_number", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("ssn", re.compile(r"\b\d{3}[- ]\d{2}[- ]\d{4}\b")),
    # Before the bare nine-digit rule: an ABA routing number is nine digits, and
    # "routing number 021000021" should be reported as what it is.
    ("bank_account", re.compile(
        r"\b(?:account|acct|routing|aba)\s*(?:number|no\.?|#)?\s*[:#]?\s*\d{4,17}\b", re.I)),
    # Nine bare digits: an SSN written without dashes, or a FEMA registration
    # number. Both are exactly what a scammer asks for.
    ("nine_digit_id", re.compile(r"(?<![\d-])\d{9}(?![\d-])")),
    ("date_of_birth", re.compile(
        r"\b(?:born(?: on)?|dob|date of birth|birthday)\s*[:\-]?\s*"
        r"(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|[A-Za-z]{3,9}\.? \d{1,2},? \d{4})", re.I)),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("phone", re.compile(r"(?<!\d)(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}(?!\d)")),
    ("street_address", re.compile(
        r"\b\d{1,6}\s+(?:[NSEW]\.?\s+)?[A-Z][\w'-]*(?:\s+[A-Z][\w'-]*){0,3}\s+"
        r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Court|Ct|"
        r"Circle|Cir|Parkway|Pkwy|Highway|Hwy|Way|Place|Pl|Terrace|Trail)\b\.?")),
]

WHY = {
    "card_number": "a payment card number",
    "ssn": "a Social Security number",
    "nine_digit_id": "a nine-digit number (a Social Security or FEMA registration number)",
    "bank_account": "a bank account or routing number",
    "date_of_birth": "a date of birth",
    "email": "an email address",
    "phone": "a phone number",
    "street_address": "a street address",
}


@dataclass
class Redaction:
    text: str
    removed: list[str] = field(default_factory=list)

    @property
    def any(self) -> bool:
        return bool(self.removed)

    def notice(self) -> str | None:
        if not self.removed:
            return None
        kinds = sorted({WHY[k] for k in self.removed})
        return (
            "We removed " + ", ".join(kinds) + " from what you typed and did not keep it. "
            "You never need to share these here. Share them only on the official "
            "application at DisasterAssistance.gov or with the FEMA Helpline you called yourself."
        )

    def to_dict(self) -> dict:
        return {"removed": sorted(set(self.removed)), "notice": self.notice()}


def redact(text: str | None) -> Redaction:
    """Remove identifiers. The only function in this module that sees raw input."""
    if not text:
        return Redaction(text="")
    out = text
    removed: list[str] = []
    for kind, pattern in RULES:
        def repl(m: re.Match[str], kind=kind) -> str:
            if kind == "card_number":
                digits = re.sub(r"\D", "", m.group(0))
                if not (13 <= len(digits) <= 19 and _luhn_ok(digits)):
                    return m.group(0)
            removed.append(kind)
            return f"[removed {kind.replace('_', ' ')}]"

        out = pattern.sub(repl, out)
    return Redaction(text=out, removed=removed)
