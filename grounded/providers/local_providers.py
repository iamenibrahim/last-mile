"""Local implementations of every provider interface.

These exist so the demo cannot be killed by a throttled key, a misnamed
deployment, or a conference-wifi outage (brief section 12).

HONESTY NOTE, and it matters for the pitch: these are stubs, not competitors to
the Azure services. Specifically:

  * LocalTranslator is a glossary-driven word-substitution engine, not machine
    translation. It is invertible by construction, which makes the offline
    back-translation check meaningful as a *plumbing* test of the verifier, but
    it is not evidence of translation quality. Never report a chrF++ number
    computed against this engine as a translation-quality result.
  * LocalEmbedder is a hashed bag-of-words vectoriser. Cosine similarity over it
    measures lexical overlap, not semantics. `semantic = False` so the eval
    report can label the number correctly.
  * LocalJudge is a rule-based entailment check over numbers, entities and
    negation, not an LLM judge. `llm_backed = False` for the same reason.

Every one of these sets `name` to a string starting with "local-", and that
string is written into the manifest transform chain. A reader of the artifact
can always tell which engine produced it.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import re
import struct
import subprocess
import tempfile
from pathlib import Path
from typing import Sequence

from .. import config

# ---------------------------------------------------------------------------
# Shared text utilities
# ---------------------------------------------------------------------------

SENTINEL_RE = re.compile(r"\[\[E\d+\]\]")
WORD_RE = re.compile(r"[A-Za-z']+")


def _protect_sentinels(text: str) -> tuple[str, list[str]]:
    """Pull sentinels out so downstream string mangling cannot touch them."""
    found: list[str] = []

    def repl(m: re.Match[str]) -> str:
        found.append(m.group(0))
        return f"\x00{len(found) - 1}\x00"

    return SENTINEL_RE.sub(repl, text), found


def _restore_sentinels(text: str, found: list[str]) -> str:
    for i, s in enumerate(found):
        text = text.replace(f"\x00{i}\x00", s)
    return text


def split_sentences(text: str) -> list[str]:
    """Sentence splitter that refuses to break inside a sentinel or a number.

    NWS text is full of "3.5 feet" and "I-81", so a naive split on "." shreds
    exactly the entities we care most about.
    """
    if not text:
        return []
    guarded, found = _protect_sentinels(text)
    # Protect decimals and common abbreviations from the splitter.
    guarded = re.sub(r"(\d)\.(\d)", "\\1\x01\\2", guarded)
    for abbr in ("Mr.", "Mrs.", "Dr.", "St.", "Ave.", "Rd.", "Hwy.", "U.S.", "a.m.", "p.m.", "No."):
        guarded = guarded.replace(abbr, abbr.replace(".", "\x02"))
    parts = re.split(r"(?<=[.!?])\s+", guarded)
    out: list[str] = []
    for p in parts:
        p = p.replace("\x01", ".").replace("\x02", ".")
        p = _restore_sentinels(p, found).strip()
        if p:
            out.append(p)
    return out


# ---------------------------------------------------------------------------
# Glossary-driven local translator
# ---------------------------------------------------------------------------

GLOSSARY_DIR = config.DATA_DIR / "glossary"


def _load_glossary(lang: str) -> dict[str, str]:
    path = GLOSSARY_DIR / f"{lang}.json"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        raw = json.load(fh)
    return {k.lower(): v for k, v in raw.get("entries", {}).items()}


class LocalTranslator:
    """Glossary substitution. Deterministic, invertible, sentinel-safe.

    Multi-word phrases are matched longest-first so that "high ground" wins over
    "high" + "ground". Anything not in the glossary is left in English, which is
    itself informative: the verifier's coverage check sees the untranslated
    residue and the segment abstains rather than shipping a half-translation.
    """

    name = "local-glossary-substitution"

    def __init__(self) -> None:
        self._fwd: dict[str, dict[str, str]] = {}
        self._rev: dict[str, dict[str, str]] = {}

    def _glossary(self, lang: str) -> tuple[dict[str, str], dict[str, str]]:
        if lang not in self._fwd:
            fwd = _load_glossary(lang)
            self._fwd[lang] = fwd
            rev: dict[str, str] = {}
            for en, tgt in fwd.items():
                rev.setdefault(tgt.lower(), en)
            self._rev[lang] = rev
        return self._fwd[lang], self._rev[lang]

    def detect(self, text: str) -> str:
        # The pipeline only ever ingests NWS English products.
        return "en"

    @staticmethod
    def _substitute(text: str, table: dict[str, str]) -> str:
        if not table:
            return text
        guarded, found = _protect_sentinels(text)
        keys = sorted(table, key=len, reverse=True)
        pattern = re.compile(
            r"(?<![\w'])(" + "|".join(re.escape(k) for k in keys) + r")(?![\w'])",
            re.IGNORECASE,
        )

        def repl(m: re.Match[str]) -> str:
            return table[m.group(1).lower()]

        return _restore_sentinels(pattern.sub(repl, guarded), found)

    def translate(self, texts: Sequence[str], target: str, source: str = "en") -> list[str]:
        if target == "en":
            fwd = self._rev.get(source) or self._glossary(source)[1]
            return [self._substitute(t, fwd) for t in texts]
        fwd, _ = self._glossary(target)
        return [self._substitute(t, fwd) for t in texts]

    def back_translate(self, texts: Sequence[str], source_lang: str) -> list[str]:
        _, rev = self._glossary(source_lang)
        return [self._substitute(t, rev) for t in texts]


# ---------------------------------------------------------------------------
# Rule-based simplifier
# ---------------------------------------------------------------------------

# NWS register -> plain English. Chosen for the two things Flesch-Kincaid
# actually measures: syllables per word and words per sentence.
PLAIN_LEXICON: dict[str, str] = {
    "accumulation": "build up",
    "accumulations": "build ups",
    "additional": "more",
    "adjacent": "next",
    "advisory": "warning",
    "anticipated": "expected",
    "approximately": "about",
    "assistance": "help",
    "attempt": "try",
    "avoid traveling": "do not travel",
    "capable of": "able to",
    "caution": "care",
    "commence": "start",
    "communicate": "tell",
    "consider seeking shelter": "go inside",
    "currently": "now",
    "damaging": "harmful",
    "deteriorate": "get worse",
    "determine": "find out",
    "developing": "forming",
    "discontinue": "stop",
    "dissipating": "ending",
    "elevated": "higher",
    "eliminate": "remove",
    "encounter": "meet",
    "ensure": "make sure",
    "evacuate": "leave",
    "evacuation": "leaving",
    "excessive": "too much",
    "exercise caution": "be careful",
    "expedite": "hurry",
    "experiencing": "having",
    "facilitate": "help",
    "hazardous": "dangerous",
    "hazards": "dangers",
    "hazard": "danger",
    "immediately": "now",
    "impacts": "effects",
    "imminent": "about to happen",
    "in the vicinity of": "near",
    "indicate": "show",
    "indicated": "showed",
    "initiate": "start",
    "inundated": "flooded",
    "inundation": "flooding",
    "isolated": "a few",
    "life threatening": "deadly",
    "life-threatening": "deadly",
    "locate": "find",
    "location": "place",
    "locations": "places",
    "maintain": "keep",
    "minimal": "small",
    "mitigate": "reduce",
    "motorists": "drivers",
    "numerous": "many",
    "observe": "watch",
    "obtain": "get",
    "occur": "happen",
    "occurring": "happening",
    "ongoing": "still going",
    "originating": "starting",
    "participate": "take part",
    "pedestrians": "people walking",
    "personnel": "staff",
    "portions": "parts",
    "potential": "chance",
    "precipitation": "rain",
    "prior to": "before",
    "proceed": "go",
    "prohibited": "not allowed",
    "prolonged": "long",
    "promptly": "right away",
    "provide": "give",
    "purchase": "buy",
    "recommend": "tell you",
    "region": "area",
    "relocate": "move",
    "remain": "stay",
    "remainder": "rest",
    "request": "ask",
    "require": "need",
    "residences": "homes",
    "residents": "people",
    "respond": "act",
    "restrictions": "limits",
    "resume": "start again",
    "saturated": "soaked",
    "significant": "big",
    "subsequently": "later",
    "sufficient": "enough",
    "sustain": "keep",
    "terminate": "end",
    "thunderstorms": "storms",
    "thunderstorm": "storm",
    "transportation": "travel",
    "turn around dont drown": "turn around, do not drown",
    "utilize": "use",
    "vehicles": "cars",
    "vehicle": "car",
    "vicinity": "area",
    "visibility": "how far you can see",
    "anticipate": "expect",
    "monitor": "watch",
    "advise": "tell",
    "sheltering": "staying safe inside",
    # Second pass, chosen from a frequency count of polysyllabic words in the
    # real cached corpus rather than guessed. Proper nouns dominate that list
    # and are deliberately absent here: they are locked entities and must
    # survive verbatim, whatever it costs the readability score.
    "expected": "likely",
    "affecting": "hitting",
    "affected": "hit",
    "encountering": "reaching",
    "encounters": "reaches",
    "impacted": "hit",
    "experience": "have",
    "following": "these",
    "continues": "goes on",
    "unsecured": "loose",
    "barricades": "road blocks",
    "barricade": "road block",
    "especially": "very",
    "information": "news",
    "recognize": "see",
    "available": "ready",
    "reported": "said",
    "reporting": "saying",
    "including": "like",
    "extended": "made longer",
    "earlier": "before",
    "located": "was",
    "agricultural": "farm",
    "interior": "inside",
    "areas": "places",
    "possible": "may happen",
    "quickly": "fast",
    "rapidly": "fast",
    "suddenly": "all at once",
    "dangerous": "not safe",
    "unnecessary": "not needed",
    "difficult": "hard",
    "entering": "going into",
    "covered": "under water",
    "roadway": "road",
    "roadways": "roads",
    "waterways": "rivers",
    "structures": "buildings",
    "structure": "building",
}

# Sentence-level rewrites that survive without a model.
PHRASE_REWRITES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bit is (?:highly )?recommended that you\b", re.I), "you should"),
    (re.compile(r"\bthere is the potential for\b", re.I), "there may be"),
    (re.compile(r"\bin order to\b", re.I), "to"),
    (re.compile(r"\bdue to the fact that\b", re.I), "because"),
    (re.compile(r"\bat the present time\b", re.I), "now"),
    (re.compile(r"\bis expected to be\b", re.I), "will be"),
    (re.compile(r"\bwill be in effect\b", re.I), "lasts"),
    (re.compile(r"\bare advised to\b", re.I), "should"),
    (re.compile(r"\bis advised to\b", re.I), "should"),
    (re.compile(r"\bplease be advised that\b", re.I), ""),
    (re.compile(r"\bbe aware of your surroundings\b", re.I), "watch what is around you"),
]

MAX_WORDS_PER_SENTENCE = 14
SPLIT_CONNECTIVES = re.compile(
    r",\s+(?:and|but|which|while|as well as|in addition to)\s+|;\s+", re.I
)


class LocalSimplifier:
    """Deterministic plain-language rewriter.

    This is a real simplifier, not a placeholder: it lowers Flesch-Kincaid grade
    by shortening sentences and swapping polysyllabic bureaucratic vocabulary.
    The FK numbers in the eval report are therefore honest even with no Azure
    OpenAI key. What it cannot do is reorganise or summarise - and it is not
    supposed to. The abstention layer sits downstream either way.
    """

    name = "local-rule-simplifier"
    _PROMPT_ID = "local-rule-simplifier/v1.2"

    @property
    def prompt_sha256(self) -> str:
        return hashlib.sha256(self._PROMPT_ID.encode()).hexdigest()

    def simplify(self, text: str, target_grade: float = 7.0, lang: str = "en",
                 protect: frozenset[str] = frozenset()) -> str:
        if not text.strip():
            return text
        guarded, found = _protect_sentinels(text)
        for pattern, repl in PHRASE_REWRITES:
            guarded = pattern.sub(repl, guarded)
        guarded = self._swap_lexicon(guarded, protect)
        sentences = split_sentences(guarded)
        out: list[str] = []
        for s in sentences:
            out.extend(self._shorten(s))
        result = " ".join(out)
        result = re.sub(r"\s+", " ", result).strip()
        result = re.sub(r"\s+([.,!?])", r"\1", result)
        return _restore_sentinels(result, found)

    @staticmethod
    def _swap_lexicon(text: str, protect: frozenset[str] = frozenset()) -> str:
        # `protect` is the calling product's vocabulary of record. In disaster
        # benefits, "assistance" is a term of art - "Rental Assistance" is what
        # a caller has to say to the FEMA Helpline - so the navigator protects
        # it, while the alert product is free to plain-language it to "help".
        guarded_words = {w.lower() for w in protect}
        keys = sorted((k for k in PLAIN_LEXICON if k.lower() not in guarded_words),
                      key=len, reverse=True)
        pattern = re.compile(r"(?<![\w'])(" + "|".join(re.escape(k) for k in keys) + r")(?![\w'])", re.I)

        def repl(m: re.Match[str]) -> str:
            src = m.group(1)
            dst = PLAIN_LEXICON[src.lower()]
            if src[:1].isupper():
                dst = dst[:1].upper() + dst[1:]
            return dst

        return pattern.sub(repl, text)

    @staticmethod
    def _shorten(sentence: str) -> list[str]:
        words = sentence.split()
        if len(words) <= MAX_WORDS_PER_SENTENCE:
            return [sentence]
        pieces = [p.strip() for p in SPLIT_CONNECTIVES.split(sentence) if p and p.strip()]
        if len(pieces) <= 1:
            return [sentence]
        fixed: list[str] = []
        for p in pieces:
            p = p[:1].upper() + p[1:]
            if not p.endswith((".", "!", "?")):
                p += "."
            fixed.append(p)
        return fixed


# ---------------------------------------------------------------------------
# Hashed bag-of-words embedder
# ---------------------------------------------------------------------------


class LocalEmbedder:
    """Hashing vectoriser. Lexical overlap only - see module docstring."""

    name = "local-hashed-bow"
    semantic = False
    DIM = 512

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.DIM
        tokens = [w.lower() for w in WORD_RE.findall(text)]
        # Unigrams plus bigrams: bigrams give the check a thin grip on word
        # order, which is what catches a dropped negation moving "not".
        grams = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
        for g in grams:
            h = int(hashlib.md5(g.encode()).hexdigest()[:8], 16)
            vec[h % self.DIM] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    da = math.sqrt(sum(x * x for x in a)) or 1.0
    db = math.sqrt(sum(y * y for y in b)) or 1.0
    return num / (da * db)


# ---------------------------------------------------------------------------
# Rule-based entailment judge
# ---------------------------------------------------------------------------

NEGATIONS = {
    "not", "never", "no", "dont", "don't", "do not", "cannot", "can't",
    "avoid", "refrain", "without", "none", "stop",
}
NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)?\b")


class LocalJudge:
    """Grounding check without an LLM.

    Four rules, each aimed at a failure that actually occurs:
      1. invented numbers
      2. flipped polarity
      3. document-level vocabulary drift
      4. an inserted *sentence* with no support in the source

    Rule 4 exists because rules 1-3 are all ratios over the whole segment, and
    a ratio hides an insertion: appending one fabricated sentence to a long
    paragraph barely moves a document-level number while being precisely the
    failure that matters. Grounding has to be checked at the granularity at
    which claims are made, which is the sentence.

    The source anchor set is expanded with the simplifier's own lexicon images -
    if the source says "inundation", "flooding" counts as supported - because
    otherwise every licensed simplification reads as unsupported content. That
    coupling is deliberate and is why this is a floor, not a judge: it knows
    what the local simplifier is allowed to do and nothing more. An LLM judge
    needs no such hint, which is the point of the Azure path.
    """

    name = "local-rule-entailment"
    llm_backed = False
    # A candidate sentence needs this share of its content words anchored in
    # the source to count as supported.
    SENTENCE_SUPPORT_FLOOR = 0.4

    def entails(self, source: str, candidate: str) -> tuple[bool, float, str]:
        src_nums = set(NUMBER_RE.findall(source))
        cand_nums = set(NUMBER_RE.findall(candidate))
        invented = cand_nums - src_nums
        if invented:
            return False, 0.0, f"output asserts number(s) absent from source: {sorted(invented)}"

        src_neg = self._negation_count(source)
        cand_neg = self._negation_count(candidate)
        if src_neg and cand_neg == 0:
            return False, 0.2, "source is negated ('do not ...') but output carries no negation"
        if cand_neg > src_neg + 1:
            return False, 0.3, "output introduces negation not present in source"

        src_tokens = self._expanded_anchors(source)
        cand_tokens = {w.lower() for w in WORD_RE.findall(candidate) if len(w) > 3}
        if not cand_tokens:
            return True, 1.0, "empty candidate"

        unsupported = cand_tokens - src_tokens
        ratio = 1.0 - (len(unsupported) / len(cand_tokens))
        if ratio < 0.25:
            return False, ratio, "most content words in the output do not appear in the source"

        worst = self._weakest_sentence(candidate, src_tokens)
        if worst is not None:
            score, sentence = worst
            if score < self.SENTENCE_SUPPORT_FLOOR:
                return (
                    False,
                    round(score, 3),
                    f"unsupported sentence: {sentence[:70]!r} has no anchor in the source",
                )
        return True, ratio, "no invented numbers, polarity preserved, every sentence anchored"

    @classmethod
    def _weakest_sentence(cls, candidate: str, src_tokens: set[str]):
        worst = None
        for sentence in split_sentences(candidate):
            tokens = {w.lower() for w in WORD_RE.findall(sentence) if len(w) > 3}
            # Too short to judge: a three-word imperative has no room for a ratio.
            if len(tokens) < 3:
                continue
            score = len(tokens & src_tokens) / len(tokens)
            if worst is None or score < worst[0]:
                worst = (score, sentence)
        return worst

    @staticmethod
    def _expanded_anchors(source: str) -> set[str]:
        tokens = {w.lower() for w in WORD_RE.findall(source) if len(w) > 3}
        expanded = set(tokens)
        low = source.lower()
        for src_phrase, plain in PLAIN_LEXICON.items():
            if src_phrase in low:
                expanded |= {w.lower() for w in WORD_RE.findall(plain) if len(w) > 3}
        return expanded

    @staticmethod
    def _negation_count(text: str) -> int:
        low = text.lower()
        return sum(1 for n in NEGATIONS if re.search(rf"(?<![\w']){re.escape(n)}(?![\w'])", low))


# ---------------------------------------------------------------------------
# Speech
# ---------------------------------------------------------------------------


class LocalSpeech:
    """Windows SAPI where available, otherwise an audible placeholder tone.

    The placeholder is never passed off as speech: `synthesize` returns a mime
    type and the caller writes `engine` into the manifest, so a rendered page
    built on the tone says so.
    """

    name = "local-sapi"

    def synthesize(self, text: str, lang: str) -> tuple[bytes, str]:
        clean = re.sub(r"\s+", " ", text).strip()
        if os.name == "nt":
            try:
                return self._sapi(clean), "audio/wav"
            except Exception:
                pass
        return self._tone(), "audio/wav"

    @staticmethod
    def _sapi(text: str) -> bytes:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.wav"
            txt = Path(td) / "in.txt"
            txt.write_text(text, encoding="utf-8")
            script = (
                "Add-Type -AssemblyName System.Speech; "
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"$s.SetOutputToWaveFile('{out}'); "
                f"$t = Get-Content -Raw -Encoding UTF8 '{txt}'; "
                "$s.Rate = -1; $s.Speak($t); $s.Dispose();"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                check=True,
                capture_output=True,
                timeout=60,
            )
            return out.read_bytes()

    @staticmethod
    def _tone(seconds: float = 0.6, freq: int = 440, rate: int = 16000) -> bytes:
        frames = int(seconds * rate)
        data = b"".join(
            struct.pack("<h", int(12000 * math.sin(2 * math.pi * freq * i / rate)))
            for i in range(frames)
        )
        hdr = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt "
        hdr += struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
        hdr += b"data" + struct.pack("<I", len(data))
        return hdr + data


# ---------------------------------------------------------------------------
# Content safety
# ---------------------------------------------------------------------------


class LocalContentSafety:
    """Output guard. Narrow by design: this pipeline only ever paraphrases an
    authoritative government product, so the realistic failure is a mangled
    render, not harmful generation."""

    name = "local-guard"

    def check(self, text: str) -> tuple[bool, list[str]]:
        flags: list[str] = []
        if SENTINEL_RE.search(text):
            flags.append("unrestored_sentinel")
        if "�" in text:
            flags.append("encoding_damage")
        if len(text.strip()) == 0:
            flags.append("empty_render")
        return (not flags), flags


# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------


class LocalHmacSigner:
    """HMAC-SHA256 with a dev key on disk.

    Symmetric, so anyone who can verify can also forge. That is fine for a
    prototype and is stated plainly in the manifest via `key_id`; the Key Vault
    signer is the asymmetric path.
    """

    name = "local-hmac-sha256"
    key_id = "local-dev-hmac-v1"
    algorithm = "HMAC-SHA256"

    def __init__(self) -> None:
        # A shared MANIFEST_SIGNING_KEY lets several instances verify each
        # other's signatures; otherwise each machine generates its own key.
        shared = os.environ.get("MANIFEST_SIGNING_KEY", "")
        if shared and not shared.startswith("replace-with"):
            self._key = shared.encode("utf-8")
            return
        path = config.LOCAL_SIGNING_KEY_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(os.urandom(32))
        self._key = path.read_bytes()

    def sign(self, payload: bytes) -> str:
        return hmac.new(self._key, payload, hashlib.sha256).hexdigest()

    def verify(self, payload: bytes, signature: str) -> bool:
        return hmac.compare_digest(self.sign(payload), signature)

    def public_jwk(self) -> None:
        """Symmetric: there is no public half to publish."""
        return None
