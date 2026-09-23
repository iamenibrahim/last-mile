"""The pipeline: lock -> simplify -> translate -> verify -> abstain or emit.

Brief sections 3.1 and 3.3.

ORDER, and a deliberate deviation from the brief's illustrative manifest. The
brief sketches `translate` then `simplify`. This implementation simplifies
first, then translates, because:

  * simplified English is markedly easier to translate well, so the target text
    inherits the reading-level win instead of fighting for it;
  * a target-language simplifier would have to be trusted per language, and the
    local fallback has no such capability at all.

`TRANSFORM_ORDER=translate_first` switches it back, and whichever order ran is
what the manifest's transform_chain records. The chain is a log, not a label.

WHAT THE CHECKS COMPARE. Every check runs on *masked* text with sentinels
stripped from both sides - masked source against masked back-translation. That
is the only apples-to-apples comparison available: entity preservation is
already guaranteed structurally by check 1, so leaving entity surface forms in
one side and not the other would just add noise to checks 2-4.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from . import actions, config, entities as ent, geo, verify as vf
from .providers.base import get_registry
from .providers.local_providers import LocalTranslator, split_sentences

TRANSFORM_ORDER = os.environ.get("TRANSFORM_ORDER", "simplify_first")
THRESHOLDS_PATH = config.REPO_ROOT / "grounded_eval" / "thresholds.json"


def load_thresholds() -> dict:
    """Thresholds tuned by the eval harness, if it has run. Engine-scoped,
    because a lexical embedder and a learned one do not share a scale."""
    if THRESHOLDS_PATH.exists():
        try:
            with THRESHOLDS_PATH.open(encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}
    return {}


@dataclass
class Segment:
    id: str
    role: str  # "headline" | "description" | "instruction"
    source_text: str
    required_action: bool = False
    source_span: tuple[int, int] | None = None
    step_index: int | None = None
    kind: str | None = None
    section: str | None = None
    # Free-form attachments the pipeline carries but never reads: the
    # navigator hangs each claim's citation here so it rides along with the
    # segment into the render and the manifest.
    meta: dict = field(default_factory=dict)

    # filled in by the pipeline
    masked_source: str = ""
    entities: list[ent.Entity] = field(default_factory=list)
    simplified_en: str = ""
    masked_output: str = ""
    back_translated: str = ""
    output_text: str = ""
    status: str = "pending"
    reason: str | None = None
    verdict: vf.SegmentVerdict | None = None

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "role": self.role,
            "kind": self.kind,
            "section": self.section,
            "step_index": self.step_index,
            "source_text": self.source_text,
            "output_text": self.output_text,
            "status": self.status,
            "reason": self.reason,
            "required_action": self.required_action,
            "entities": [e.to_dict() for e in self.entities],
            "entity_count": len(self.entities),
        }
        if self.source_span:
            d["source_span"] = list(self.source_span)
        if self.verdict:
            d["checks"] = [c.to_dict() for c in self.verdict.checks]
        if self.meta:
            d["meta"] = self.meta
        return d


ABSTAIN_LABEL = "original text shown - machine translation withheld"


# ---------------------------------------------------------------------------
# Segmentation
# ---------------------------------------------------------------------------

# NWS descriptions are structured: "* WHAT...", "* WHERE...", "HAZARD...",
# "IMPACT...". Those labels are scaffolding, not prose. Feeding them to a
# simplifier is how "IMPACTS" comes back as "Effects" - a structural field name
# silently rewritten. They are lifted out, rendered from a fixed table, and
# never sent through a model.
NWS_SECTION = re.compile(r"(?m)^\s*\*?\s*([A-Z][A-Z /]{2,25}?)\s*\.{2,}\s*")

SECTION_LABELS: dict[str, dict[str, str]] = {
    "en": {"WHAT": "What", "WHERE": "Where", "WHEN": "When", "IMPACTS": "What it means for you",
           "IMPACT": "What it means for you", "HAZARD": "Hazard", "SOURCE": "How we know",
           "ADDITIONAL DETAILS": "More detail", "PRECAUTIONARY/PREPAREDNESS ACTIONS": "What to do"},
    "es": {"WHAT": "Que", "WHERE": "Donde", "WHEN": "Cuando", "IMPACTS": "Lo que significa para usted",
           "IMPACT": "Lo que significa para usted", "HAZARD": "Peligro", "SOURCE": "Como lo sabemos",
           "ADDITIONAL DETAILS": "Mas detalles", "PRECAUTIONARY/PREPAREDNESS ACTIONS": "Que hacer"},
    "tl": {"WHAT": "Ano", "WHERE": "Saan", "WHEN": "Kailan", "IMPACTS": "Ano ang ibig sabihin nito",
           "IMPACT": "Ano ang ibig sabihin nito", "HAZARD": "Panganib", "SOURCE": "Paano namin alam",
           "ADDITIONAL DETAILS": "Karagdagang detalye", "PRECAUTIONARY/PREPAREDNESS ACTIONS": "Ano ang gagawin"},
    "ar": {"WHAT": "ماذا", "WHERE": "أين", "WHEN": "متى",
           "IMPACTS": "ما يعنيه لك", "IMPACT": "ما يعنيه لك",
           "HAZARD": "خطر", "SOURCE": "المصدر",
           "ADDITIONAL DETAILS": "تفاصيل إضافية",
           "PRECAUTIONARY/PREPAREDNESS ACTIONS": "ماذا تفعل"},
    "prs": {"WHAT": "چی", "WHERE": "کجا", "WHEN": "کی",
            "IMPACTS": "برای شما چه معنا دارد",
            "IMPACT": "برای شما چه معنا دارد",
            "HAZARD": "خطر", "SOURCE": "منبع",
            "ADDITIONAL DETAILS": "جزئیات بیشتر",
            "PRECAUTIONARY/PREPAREDNESS ACTIONS": "چه کار کنید"},
}


def section_label(label: str | None, lang: str) -> str | None:
    if not label:
        return None
    table = SECTION_LABELS.get(lang) or SECTION_LABELS["en"]
    return table.get(label.upper()) or SECTION_LABELS["en"].get(label.upper()) or label.title()


def _unwrap(text: str) -> str:
    text = re.sub(r"\n(?!\n)", " ", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def parse_description(raw: str) -> list[tuple[str | None, str]]:
    """Split an NWS description into (section_label, body) pairs."""
    text = raw or ""
    # Drop the AFOS product id line ("FFWFWD", "TORILX") - routing metadata.
    text = re.sub(r"^[A-Z]{4,8}\s*\n+", "", text)

    marks = list(NWS_SECTION.finditer(text))
    if not marks:
        return [(None, _unwrap(p)) for p in re.split(r"\n\s*\n", text) if p.strip()]

    out: list[tuple[str | None, str]] = []
    preamble = text[: marks[0].start()].strip()
    if preamble:
        out.append((None, _unwrap(preamble)))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[m.end() : end].strip()
        # "- " sub-bullets inside ADDITIONAL DETAILS
        body = re.sub(r"(?m)^\s*-\s+", "\n\n", body).strip()
        for chunk in re.split(r"\n\s*\n", body):
            chunk = _unwrap(chunk)
            if chunk:
                out.append((m.group(1).strip(), chunk))
    return out


def build_segments(properties: dict) -> tuple[list[Segment], list[actions.Step]]:
    segments: list[Segment] = []
    n = 0

    headline = (properties.get("headline") or "").strip()
    if headline:
        n += 1
        segments.append(Segment(id=f"s{n}", role="headline", source_text=headline))

    for label, body in parse_description(properties.get("description") or ""):
        for sentence in split_sentences(body):
            if not sentence.strip():
                continue
            n += 1
            segments.append(
                Segment(id=f"s{n}", role="description", source_text=sentence.strip(),
                        section=label)
            )

    steps = actions.parse_instruction(properties.get("instruction"))
    for step in steps:
        n += 1
        segments.append(
            Segment(
                id=f"s{n}",
                role="instruction",
                source_text=step.text,
                required_action=step.required,
                source_span=step.source_span,
                step_index=step.index,
                kind=step.kind,
            )
        )
    return segments, steps


# ---------------------------------------------------------------------------
# The pipeline
# ---------------------------------------------------------------------------


def _gazetteer_for(properties: dict) -> ent.Gazetteer:
    g = ent.Gazetteer.load()
    g.add_from_area_desc(properties.get("areaDesc") or "")
    return g


def _back_translate(registry, texts: list[str], lang: str) -> list[str]:
    """Round-trip the target text back to English for checks 2-4."""
    if not texts:
        return []
    translator = registry.translator
    if isinstance(translator, LocalTranslator):
        return translator.back_translate(texts, lang)
    return translator.translate(texts, target="en", source=lang)


def run_pipeline(
    segments: list[Segment],
    lang: str,
    target_grade: float,
    gazetteer: ent.Gazetteer | None,
    corrupt_fn=None,
    lock_entities: bool = True,
    protect_terms: frozenset[str] = frozenset(),
) -> dict:
    """Stages 1-4 plus the output guard, over any list of segments.

    Shared by the alert transformer and the disaster-assistance navigator, so
    both products get the same lock -> simplify -> translate -> verify ->
    abstain behaviour from one implementation rather than two that can drift.
    Mutates the segments in place and returns the bookkeeping.
    """
    registry = get_registry()
    thresholds = load_thresholds().get(registry.embedder.name, {})

    order = TRANSFORM_ORDER
    chain: list[dict[str, Any]] = []
    total_entities = 0

    # --- Stage 1: entity lock -------------------------------------------------
    # lock_entities=False is the ablation arm used by eval/metrics.py to measure
    # what the other three checks catch on their own. It is never a runtime path.
    for seg in segments:
        if lock_entities:
            locked = ent.lock(seg.source_text, gazetteer)
            seg.masked_source = locked.masked
            seg.entities = locked.entities
            total_entities += len(locked.entities)
        else:
            seg.masked_source = seg.source_text
            seg.entities = []
    chain.append({"step": "entity_lock", "version": ent.VERSION, "entities": total_entities,
                  "gazetteer_names": len(gazetteer), "enabled": lock_entities})

    # --- Stage 2: transform ---------------------------------------------------
    simplifier = registry.simplifier
    translator = registry.translator

    def simplify_all(texts: list[str], in_lang: str) -> list[str]:
        return [simplifier.simplify(t, target_grade, in_lang, protect_terms) for t in texts]

    masked_inputs = [s.masked_source for s in segments]

    if lang == "en":
        outputs = simplify_all(masked_inputs, "en")
        for seg, out in zip(segments, outputs):
            seg.simplified_en = out
            seg.masked_output = out
            seg.back_translated = out  # no round trip needed
        chain.append({"step": "simplify", "engine": simplifier.name,
                      "target_grade": target_grade,
                      "prompt_sha256": simplifier.prompt_sha256})
    elif order == "translate_first":
        translated = translator.translate(masked_inputs, target=lang, source="en")
        chain.append({"step": "translate", "engine": translator.name, "target": lang})
        simplified = [simplifier.simplify(t, target_grade, lang, protect_terms) for t in translated]
        chain.append({"step": "simplify", "engine": simplifier.name,
                      "target_grade": target_grade, "prompt_sha256": simplifier.prompt_sha256})
        for seg, out in zip(segments, simplified):
            seg.masked_output = out
        backs = _back_translate(registry, simplified, lang)
        for seg, b in zip(segments, backs):
            seg.back_translated = b
        chain.append({"step": "back_translate", "engine": translator.name, "source": lang})
    else:
        simplified = simplify_all(masked_inputs, "en")
        for seg, out in zip(segments, simplified):
            seg.simplified_en = out
        chain.append({"step": "simplify", "engine": simplifier.name,
                      "target_grade": target_grade, "prompt_sha256": simplifier.prompt_sha256})
        translated = translator.translate(simplified, target=lang, source="en")
        chain.append({"step": "translate", "engine": translator.name, "target": lang})
        for seg, out in zip(segments, translated):
            seg.masked_output = out
        backs = _back_translate(registry, translated, lang)
        for seg, b in zip(segments, backs):
            seg.back_translated = b
        chain.append({"step": "back_translate", "engine": translator.name, "source": lang})

    # --- Injection hook (eval harness / refusal demo) -------------------------
    corrupted_ids: list[str] = []
    if corrupt_fn is not None:
        for seg in segments:
            damaged = corrupt_fn(seg.id, seg.masked_output)
            if damaged is not None and damaged != seg.masked_output:
                seg.masked_output = damaged
                corrupted_ids.append(seg.id)
        if lang == "en":
            for seg in segments:
                seg.back_translated = seg.masked_output
        else:
            backs = _back_translate(registry, [s.masked_output for s in segments], lang)
            for seg, b in zip(segments, backs):
                seg.back_translated = b
        chain.append({"step": "corruption_injected", "segments": corrupted_ids,
                      "note": "adversarial test input, not a production step"})

    # --- Stage 3: verify ------------------------------------------------------
    checks_passed = checks_failed = 0
    for seg in segments:
        seg.verdict = vf.verify_segment(
            segment_id=seg.id,
            source_en=seg.masked_source,
            masked_candidate=seg.masked_output,
            back_translated_en=seg.back_translated,
            locked=seg.entities,
            is_required_action=seg.required_action,
            embedder=registry.embedder,
            judge=registry.judge,
            thresholds=thresholds,
            lang=lang,
        )
        for c in seg.verdict.checks:
            if c.passed:
                checks_passed += 1
            else:
                checks_failed += 1

    # --- Stage 4: abstain policy ---------------------------------------------
    for seg in segments:
        if seg.verdict and seg.verdict.passed:
            restored, integrity = ent.unlock(seg.masked_output, seg.entities, unit_lang=lang)
            if integrity.passed:
                seg.output_text = restored
                seg.status = "translated_verified"
                seg.reason = None
                continue
            # Restoration itself can fail even when the masked text looked fine
            # (a numeral vanishing after unit localisation, say). Abstain.
            seg.reason = "entity_integrity"
            seg.status = "verbatim_abstained"
            seg.output_text = seg.source_text
            continue
        seg.status = "verbatim_abstained"
        seg.reason = seg.verdict.reason if seg.verdict else "verification_unavailable"
        seg.output_text = seg.source_text

    chain.append({"step": "verify", "checks_passed": checks_passed, "checks_failed": checks_failed,
                  "embedder": registry.embedder.name, "judge": registry.judge.name,
                  "semantic_embeddings": bool(getattr(registry.embedder, "semantic", False)),
                  "llm_judge": bool(getattr(registry.judge, "llm_backed", False))})

    # --- Output guard ---------------------------------------------------------
    rendered_blob = "\n".join(s.output_text for s in segments)
    safe, flags = registry.content_safety.check(rendered_blob)
    chain.append({"step": "content_safety", "engine": registry.content_safety.name,
                  "passed": safe, "flags": flags})
    if not safe:
        # A guard failure is document-level and unrecoverable per segment, so
        # the whole render falls back to source English rather than shipping.
        for seg in segments:
            seg.status = "verbatim_abstained"
            seg.reason = f"content_safety:{','.join(flags)}"
            seg.output_text = seg.source_text

    doc_coverage = vf.check_document_coverage(
        [s.source_text for s in segments if s.required_action],
        [s.to_dict() for s in segments],
    )

    return {
        "chain": chain,
        "order": order,
        "total_entities": total_entities,
        "corrupted_ids": corrupted_ids,
        "doc_coverage": doc_coverage,
        "registry": registry,
    }


def transform_alert(
    feature: dict,
    lang: str = "en",
    target_grade: float | None = None,
    corrupt_fn=None,
    lock_entities: bool = True,
) -> dict:
    """Run the full transform for one alert into one language.

    `corrupt_fn(segment_id, masked_output) -> masked_output` is the injection
    hook used by eval/corrupt.py and by the demo's refusal beat. It is the only
    way to damage the output, which keeps the adversarial path honest: the
    harness corrupts real output from the real pipeline rather than scoring a
    mock.
    """
    t0 = time.perf_counter()
    target_grade = config.TARGET_READING_GRADE if target_grade is None else target_grade
    properties = feature.get("properties", {})

    gazetteer = _gazetteer_for(properties)
    segments, steps = build_segments(properties)

    pr = run_pipeline(segments, lang, target_grade, gazetteer, corrupt_fn, lock_entities)
    chain, order = pr["chain"], pr["order"]
    total_entities, corrupted_ids = pr["total_entities"], pr["corrupted_ids"]
    doc_coverage, registry = pr["doc_coverage"], pr["registry"]

    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    abstained = [s for s in segments if s.status == "verbatim_abstained"]

    def seg_dict(s: Segment) -> dict:
        d = s.to_dict()
        # Section labels are rendered from a fixed table, never from a model,
        # so they cannot be rewritten and never need to abstain.
        d["section_label"] = section_label(s.section, lang)
        return d

    return {
        "render_id": uuid.uuid4().hex[:16],
        "alert_id": properties.get("id") or feature.get("id"),
        "language": lang,
        "language_name": config.SUPPORTED_LANGUAGES.get(lang, {}).get("name", "English"),
        "text_direction": config.SUPPORTED_LANGUAGES.get(lang, {}).get("dir", "ltr"),
        "created_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "target_grade": target_grade,
        "transform_order": order,
        "segments": [seg_dict(s) for s in segments],
        "steps": [seg_dict(s) for s in segments if s.role == "instruction"],
        "no_instructions_in_source": not steps,
        "instruction_note": (
            "The source alert carried no instruction field. No actions are shown "
            "because none were issued. This system does not infer actions."
            if not steps else None
        ),
        "abstained_count": len(abstained),
        "segment_count": len(segments),
        "abstention_reasons": sorted({s.reason for s in abstained if s.reason}),
        "abstain_label": ABSTAIN_LABEL,
        "document_coverage": doc_coverage.to_dict(),
        "corrupted_segments": corrupted_ids,
        "transform_chain": chain,
        "providers": registry.describe(),
        "provider_notes": registry.notes,
        "elapsed_ms": elapsed_ms,
        "entities_locked": total_entities,
    }


# ---------------------------------------------------------------------------
# Household context
# ---------------------------------------------------------------------------


def household_context(feature: dict, address: str, now: dt.datetime | None = None,
                      allow_zone_fallback: bool = True) -> dict:
    """Geometry and clock, never language (brief 3.3)."""
    located = geo.geocode(address)
    geometry, basis = geo.alert_geometry(feature, allow_zone_fallback=allow_zone_fallback)
    props = feature.get("properties", {})
    if located is None:
        relation = geo.Relation("unknown", None, False, None, basis,
                                "address could not be geocoded")
    else:
        relation = geo.relate_point(located.lat, located.lon, geometry, basis=basis)
    t = geo.timing(props, now=now)
    return {
        "address_input": address,
        "geocode": located.to_dict() if located else None,
        "relation": relation.to_dict(),
        "timing": t.to_dict(),
        "geometry": geometry,
        "geometry_basis": basis,
        "bounds": geo.polygon_bounds(geometry),
        "plain_statement": _plain_position(relation, t, props),
    }


def _plain_position(relation: geo.Relation, t: geo.Timing, props: dict) -> str:
    """The one sentence that answers 'is my house in it, and how long do I have'."""
    event = props.get("event", "alert")
    if relation.status == "inside":
        where = f"Your address is INSIDE the {event} area."
    elif relation.status == "near_edge":
        where = f"Your address is just outside the {event} area, {relation.distance_km} km from its edge."
    elif relation.status == "outside":
        where = f"Your address is OUTSIDE the {event} area, {relation.distance_km} km away."
    else:
        where = f"We could not place your address against the {event} area."

    if t.state == "before_onset":
        when = f"It {t.human}."
    elif t.state == "active":
        when = f"It is in effect now and {t.human}."
    elif t.state == "expired":
        when = f"It {t.human}."
    else:
        when = "The source gave no timing."
    return f"{where} {when}"
