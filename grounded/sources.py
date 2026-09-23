"""The authoritative document corpus, and the quote check that keeps it honest.

A navigator that paraphrases eligibility rules from memory is a navigator that
will one day tell a flood survivor something FEMA never said. So the program
catalog (data/programs.json) contains no prose of its own about what a program
does or who qualifies. Every such claim is a *verbatim quote* from a cached
authoritative document, and `locate()` finds that quote in the document by
exact match and returns its character offsets.

If a document changes and a quote no longer appears in it, the claim fails to
load and is dropped from the answer, loudly - it is never shown unsupported.
That is the same property as the alert pipeline's instruction offsets: a
citation that cannot be checked is decoration, not evidence.

Retrieval note. fema.gov and disasterassistance.gov answer scripted requests
with HTTP 403. This system does not work around that. FEMA pages enter the
corpus only as text saved from an ordinary browser view, and are marked
`retrieval: "manual"` so their provenance says exactly that.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path

from . import config

SOURCES_DIR = config.DATA_DIR / "sources"
PROGRAMS_PATH = config.DATA_DIR / "programs.json"


@dataclass
class SourceDoc:
    id: str
    title: str
    publisher: str
    url: str
    fetched_at: str
    retrieval: str  # "scripted" | "manual"
    transport: str
    text: str
    sha256: str
    note: str | None = None

    def summary(self) -> dict:
        d = asdict(self)
        d.pop("text")
        d["chars"] = len(self.text)
        return d


def normalise(text: str) -> str:
    """Whitespace-normalised form used for both storage and quote matching, so
    a quote copied from a rendered page matches regardless of line wrapping."""
    # Must stay byte-for-byte in step with NORMALISE_JS below: browser captures
    # are hashed in the page with that function and re-hashed here with this
    # one, and a single divergent character rule would reject a faithful copy.
    text = text.replace(" ", " ").replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-").replace("‑", "-")
    return re.sub(r"\s+", " ", text).strip()


NORMALISE_JS = r"""t => t.replace(/ /g,' ').replace(/[’‘]/g,"'")
  .replace(/[“”]/g,'"').replace(/[–—‑]/g,'-')
  .replace(/\s+/g,' ').trim()"""


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def save(doc_id: str, *, title: str, publisher: str, url: str, text: str,
         retrieval: str, transport: str, note: str | None = None) -> SourceDoc:
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    clean = normalise(text)
    doc = SourceDoc(
        id=doc_id,
        title=title,
        publisher=publisher,
        url=url,
        fetched_at=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        retrieval=retrieval,
        transport=transport,
        text=clean,
        sha256=text_sha256(clean),
        note=note,
    )
    (SOURCES_DIR / f"{doc_id}.json").write_text(
        json.dumps(asdict(doc), indent=1, ensure_ascii=False), encoding="utf-8"
    )
    return doc


_CACHE: dict[str, SourceDoc] | None = None


def corpus(reload: bool = False) -> dict[str, SourceDoc]:
    global _CACHE
    if _CACHE is not None and not reload:
        return _CACHE
    docs: dict[str, SourceDoc] = {}
    if SOURCES_DIR.exists():
        for path in sorted(SOURCES_DIR.glob("*.json")):
            try:
                with path.open(encoding="utf-8") as fh:
                    raw = json.load(fh)
                doc = SourceDoc(**raw)
            except Exception:
                continue
            if text_sha256(doc.text) != doc.sha256:
                # Edited after capture. Refuse it rather than cite it.
                continue
            docs[doc.id] = doc
    _CACHE = docs
    return docs


@dataclass
class Citation:
    doc_id: str
    quote: str
    start: int
    end: int
    url: str
    publisher: str
    title: str
    doc_sha256: str

    def to_dict(self) -> dict:
        return asdict(self)


def locate(doc_id: str, quote: str) -> Citation | None:
    """Find a verbatim quote in a cached document. None if it is not there."""
    doc = corpus().get(doc_id)
    if doc is None:
        return None
    needle = normalise(quote)
    start = doc.text.find(needle)
    if start < 0:
        return None
    return Citation(
        doc_id=doc.id,
        quote=needle,
        start=start,
        end=start + len(needle),
        url=doc.url,
        publisher=doc.publisher,
        title=doc.title,
        doc_sha256=doc.sha256,
    )


# ---------------------------------------------------------------------------
# Program catalog
# ---------------------------------------------------------------------------


@dataclass
class Claim:
    kind: str  # "what" | "who" | "documents" | "how_to_apply" | "deadline" | "contact" | "warning"
    citation: Citation

    def to_dict(self) -> dict:
        return {"kind": self.kind, **self.citation.to_dict()}


@dataclass
class Program:
    id: str
    name: str
    agency: str
    needs: list[str]
    gate: str  # "individual_assistance" | "any_declaration" | "always"
    gate_note: str
    claims: list[Claim]
    dropped: list[dict]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "agency": self.agency,
            "needs": self.needs,
            "gate": self.gate,
            "gate_note": self.gate_note,
            "claims": [c.to_dict() for c in self.claims],
            "dropped_claims": self.dropped,
        }


def load_programs(path: Path | None = None) -> list[Program]:
    """Load the catalog, resolving every quote. Unverifiable quotes are dropped
    and reported, never shown."""
    path = path or PROGRAMS_PATH
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        raw = json.load(fh)
    programs = []
    for p in raw.get("programs", []):
        claims, dropped = [], []
        for c in p.get("claims", []):
            cite = locate(c["doc"], c["quote"])
            if cite is None:
                dropped.append({"kind": c.get("kind"), "doc": c["doc"], "quote": c["quote"][:120],
                                "reason": "quote not found verbatim in the cached document"})
                continue
            claims.append(Claim(kind=c["kind"], citation=cite))
        programs.append(
            Program(
                id=p["id"],
                name=p["name"],
                agency=p["agency"],
                needs=p.get("needs", []),
                gate=p.get("gate", "always"),
                gate_note=p.get("gate_note", ""),
                claims=claims,
                dropped=dropped,
            )
        )
    return programs
