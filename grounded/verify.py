"""The four independent checks, and the abstain policy they feed.

Brief section 3.1, stages 3 and 4.

    check                 method                                     fails when
    entity integrity      every sentinel restored exactly once       any dropped/duped/altered
    semantic fidelity     back-translate, embed both, cosine         below threshold
    instruction coverage  each instruction sentence maps to output   a required action is missing
    grounding             entailment judge, strict rubric            output asserts what source does not

Two properties worth stating out loud because they are what make the policy
safe rather than decorative:

  1. Abstention is per segment, not per document. One bad sentence degrades one
     sentence. The document never fails whole.

  2. Abstention never reduces instruction coverage. An abstained segment is
     emitted as verbatim source English, so the instruction is still on the
     page - it is the *translation* that is withheld, not the warning. This is
     the difference between a system that refuses and a system that goes quiet.

Failure direction is always towards abstention: an unparseable judge, a
provider exception, a missing back-translation all fail closed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict, field
from typing import Sequence

from . import config, entities as ent
from .providers.local_providers import NEGATIONS, WORD_RE, cosine

# Order determines which failure is *reported* as the abstention reason when
# several fire at once; it does not affect whether a segment abstains, because
# every check runs and any failure abstains. Most specific diagnosis first:
# "the negation was lost" is actionable, "the round trip drifted" is not, and
# a dropped negation trips both. semantic_fidelity is the catch-all and so
# comes last.
CHECK_ORDER = (
    "entity_integrity",
    "translation_completeness",
    "instruction_coverage",
    "grounding",
    "semantic_fidelity",
)


@dataclass
class CheckResult:
    name: str
    passed: bool
    score: float | None
    threshold: float | None
    detail: str
    engine: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SegmentVerdict:
    segment_id: str
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def first_failure(self) -> CheckResult | None:
        for name in CHECK_ORDER:
            for c in self.checks:
                if c.name == name and not c.passed:
                    return c
        return next((c for c in self.checks if not c.passed), None)

    @property
    def status(self) -> str:
        return "translated_verified" if self.passed else "verbatim_abstained"

    @property
    def reason(self) -> str | None:
        f = self.first_failure
        return f.name if f else None

    def to_dict(self) -> dict:
        return {
            "segment_id": self.segment_id,
            "status": self.status,
            "reason": self.reason,
            "checks": [c.to_dict() for c in self.checks],
        }


# ---------------------------------------------------------------------------
# Check 1 - entity integrity
# ---------------------------------------------------------------------------


def check_entity_integrity(masked_candidate: str, locked: list[ent.Entity]) -> CheckResult:
    report = ent.check_integrity(masked_candidate, locked)
    total = len(locked) or 1
    lost = len(report.missing) + len(report.duplicated) + len(report.unexpected)
    return CheckResult(
        name="entity_integrity",
        passed=report.passed,
        score=round(max(0.0, 1.0 - lost / total), 4),
        threshold=1.0,
        detail=report.reason(),
        engine=f"entity-lock/{ent.VERSION}",
    )


# ---------------------------------------------------------------------------
# Check 2 - semantic fidelity
# ---------------------------------------------------------------------------


def _strip_sentinels(text: str) -> str:
    return re.sub(r"\s+", " ", ent.SENTINEL_RE.sub(" ", text)).strip()


def has_free_text(masked_source: str) -> bool:
    """Is there anything here a model could have paraphrased?

    A segment like "http://www.weather.gov/safety/flood" locks to a single
    sentinel and nothing else. There is no prose to check for fidelity or
    grounding, so those checks have no opinion - entity integrity is the whole
    of the verification. Treating the empty comparison as a *failure* would
    abstain on segments the pipeline handled perfectly, which is how a false
    abstention rate gets inflated by a bookkeeping artefact.
    """
    return bool(_content_anchors(_strip_sentinels(masked_source)))


def check_semantic_fidelity(source_en: str, back_translated_en: str, embedder,
                            threshold: float | None = None) -> CheckResult:
    threshold = config.SEMANTIC_FIDELITY_THRESHOLD if threshold is None else threshold
    a, b = _strip_sentinels(source_en), _strip_sentinels(back_translated_en)
    if not has_free_text(source_en):
        return CheckResult(
            "semantic_fidelity", True, None, threshold,
            "segment is entirely locked entities; nothing to paraphrase",
            getattr(embedder, "name", "?"),
        )
    if not b:
        return CheckResult(
            "semantic_fidelity", False, 0.0, threshold,
            "back-translation is empty", getattr(embedder, "name", "?"),
        )
    try:
        va, vb = embedder.embed([a, b])
        score = cosine(va, vb)
    except Exception as exc:
        # Fail closed: a check that could not run is not a check that passed.
        return CheckResult(
            "semantic_fidelity", False, None, threshold,
            f"embedding failed, abstaining: {type(exc).__name__}", getattr(embedder, "name", "?"),
        )
    semantic = getattr(embedder, "semantic", False)
    note = "cosine over learned embeddings" if semantic else "cosine over lexical bag-of-words (local stub)"
    return CheckResult(
        "semantic_fidelity", score >= threshold, round(score, 4), threshold,
        f"{note}; back-translation vs source", getattr(embedder, "name", "?"),
    )


# ---------------------------------------------------------------------------
# Check 2b - translation completeness
#
# NOT one of the brief's four. Added after the eval harness showed a real false
# negative: the output "cuando it es seguro a do so, por favor envie su
# reportes de inundacion" passed all four original checks. It is half English.
# Back-translating half-English text returns something very close to the
# source, so fidelity scores *high* precisely when the translation failed -
# the four checks are blind to this by construction, because they all compare
# English to English.
#
# Real engines fail this way too: MT services pass segments through untouched
# on timeout or on unsupported content. The check is cheap and the failure it
# catches is one a reader would notice instantly.
# ---------------------------------------------------------------------------

# Words that legitimately survive translation unchanged.
TRANSLATION_INVARIANT = {
    "radar", "doppler", "facebook", "email", "internet", "online", "gps",
    "tornado", "hospital", "taxi", "hotel", "radio", "television", "video",
    "national", "service", "county", "virginia",
}


def check_translation_completeness(masked_source_en: str, masked_output: str, lang: str,
                                   threshold: float = 0.45) -> CheckResult:
    """How much of the English survived verbatim into the target text?"""
    if lang == "en":
        return CheckResult("translation_completeness", True, None, None,
                           "English render: no translation step", "completeness/v1")
    src = _content_anchors(_strip_sentinels(masked_source_en)) - TRANSLATION_INVARIANT
    if not src:
        return CheckResult("translation_completeness", True, None, threshold,
                           "no translatable content words", "completeness/v1")
    out = _content_anchors(_strip_sentinels(masked_output))
    residue = src & out
    ratio = len(residue) / len(src)
    passed = ratio <= threshold
    sample = sorted(residue)[:5]
    return CheckResult(
        "translation_completeness", passed, round(ratio, 4), threshold,
        f"{len(residue)}/{len(src)} English content words survive verbatim in the "
        f"{lang} output"
        + (f"; e.g. {sample}" if not passed else ""),
        "completeness/v1",
    )


# ---------------------------------------------------------------------------
# Check 3 - instruction coverage
# ---------------------------------------------------------------------------


def _content_anchors(text: str) -> set[str]:
    return {w.lower() for w in WORD_RE.findall(text) if len(w) > 3}


def _negation_polarity(text: str) -> int:
    low = text.lower()
    return sum(1 for n in NEGATIONS if re.search(rf"(?<![\w']){re.escape(n)}(?![\w'])", low))


def check_instruction_coverage(source_en: str, back_translated_en: str,
                               is_required_action: bool,
                               threshold: float | None = None) -> CheckResult:
    """Does the output still carry this instruction?

    Polarity is checked first and hard: "do not cross" losing its negation is
    the single most dangerous failure this pipeline can produce, and it is not
    a matter of degree.
    """
    threshold = config.INSTRUCTION_COVERAGE_THRESHOLD if threshold is None else threshold
    src, out = _strip_sentinels(source_en), _strip_sentinels(back_translated_en)

    if is_required_action and not out.strip():
        return CheckResult("instruction_coverage", False, 0.0, threshold,
                           "required action produced empty output", "coverage/v1")

    src_neg, out_neg = _negation_polarity(src), _negation_polarity(out)
    if src_neg > 0 and out_neg == 0:
        return CheckResult(
            "instruction_coverage", False, 0.0, threshold,
            "negation lost: source prohibits an action, output does not", "coverage/v1",
        )
    if src_neg == 0 and out_neg > 0:
        return CheckResult(
            "instruction_coverage", False, 0.0, threshold,
            "negation invented: output prohibits something the source does not", "coverage/v1",
        )

    anchors = _content_anchors(src)
    if not anchors:
        return CheckResult("instruction_coverage", True, 1.0, threshold,
                           "no content anchors to check", "coverage/v1")
    kept = anchors & _content_anchors(out)
    score = len(kept) / len(anchors)
    # A simplifier is *supposed* to replace vocabulary, so the anchor ratio is
    # a floor, not an identity test. Required actions get the stricter floor.
    floor = 0.5 if is_required_action else 0.3
    return CheckResult(
        "instruction_coverage", score >= floor, round(score, 4), floor,
        f"{len(kept)}/{len(anchors)} source content words survive the round trip",
        "coverage/v1",
    )


def check_document_coverage(required_steps: Sequence[str], rendered_segments: Sequence[dict]) -> CheckResult:
    """Document level: every required action is present, translated or verbatim."""
    present = 0
    for step in required_steps:
        anchors = _content_anchors(step)
        if not anchors:
            present += 1
            continue
        for seg in rendered_segments:
            blob = f"{seg.get('source_text','')} {seg.get('output_text','')}"
            if len(anchors & _content_anchors(blob)) / len(anchors) >= 0.6:
                present += 1
                break
    total = len(required_steps) or 1
    score = present / total
    return CheckResult(
        "document_instruction_coverage", present == len(required_steps), round(score, 4), 1.0,
        f"{present}/{len(required_steps)} required actions present in the rendered document",
        "coverage/v1",
    )


# ---------------------------------------------------------------------------
# Check 4 - grounding
# ---------------------------------------------------------------------------


def check_grounding(source_en: str, back_translated_en: str, judge) -> CheckResult:
    src, out = _strip_sentinels(source_en), _strip_sentinels(back_translated_en)
    if not has_free_text(source_en):
        return CheckResult("grounding", True, None, None,
                           "segment is entirely locked entities; nothing to ground",
                           getattr(judge, "name", "?"))
    if not out:
        return CheckResult("grounding", False, 0.0, None, "empty output",
                           getattr(judge, "name", "?"))
    try:
        ok, score, reason = judge.entails(src, out)
    except Exception as exc:
        return CheckResult("grounding", False, None, None,
                           f"judge failed, abstaining: {type(exc).__name__}",
                           getattr(judge, "name", "?"))
    llm = getattr(judge, "llm_backed", False)
    prefix = "" if llm else "rule-based floor: "
    return CheckResult("grounding", bool(ok), round(float(score), 4), None,
                       prefix + reason, getattr(judge, "name", "?"))


# ---------------------------------------------------------------------------
# Stage 4 - the abstain policy
# ---------------------------------------------------------------------------


def verify_segment(segment_id: str, source_en: str, masked_candidate: str,
                   back_translated_en: str, locked: list[ent.Entity],
                   is_required_action: bool, embedder, judge,
                   thresholds: dict | None = None, lang: str = "en") -> SegmentVerdict:
    """Run every check - no short-circuit - so the report can show which classes
    of corruption each one actually catches (brief section 7)."""
    thresholds = thresholds or {}
    verdict = SegmentVerdict(segment_id=segment_id)
    verdict.checks.append(check_entity_integrity(masked_candidate, locked))
    verdict.checks.append(
        check_translation_completeness(
            source_en, masked_candidate, lang,
            thresholds.get("translation_completeness", 0.45),
        )
    )
    verdict.checks.append(
        check_semantic_fidelity(source_en, back_translated_en, embedder,
                                thresholds.get("semantic_fidelity"))
    )
    verdict.checks.append(
        check_instruction_coverage(source_en, back_translated_en, is_required_action,
                                   thresholds.get("instruction_coverage"))
    )
    verdict.checks.append(check_grounding(source_en, back_translated_en, judge))
    return verdict
