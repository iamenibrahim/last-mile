"""Disaster Assistance Navigator: where you are + what happened -> what help exists.

The division of labour is the whole design:

    DATA decides    whether your county is in a declared Individual Assistance
                    area, and how long you have (OpenFEMA; never a model)
    RULES decide    which programs to show for which needs, and the minimum
                    escalation to a human (deterministic; offline)
    QUOTES say      what each program is, who qualifies, what to bring - every
                    sentence a verbatim, offset-located quote from FEMA, eCFR,
                    SBA or SAMHSA (data/programs.json)
    MODELS do       plain language and translation only, and every model
                    output passes the same five checks as the alert pipeline,
                    abstaining per segment to the verbatim English on failure

A model never decides eligibility, never writes a program description, and
never lowers an escalation.

What is kept from a request: the county FIPS code, the need codes, the
escalation level, the language. Not the address, not the typed text.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import time
import uuid

from . import areas, config, entities as ent, escalation as esc, fema, privacy, sources
from .transform import Segment, run_pipeline

# ---------------------------------------------------------------------------
# Needs: this system's labels for the situations people describe. They are
# routing keys, not claims about any program, so they carry no citation.
# ---------------------------------------------------------------------------

NEEDS: dict[str, str] = {
    "home_damaged": "My home was damaged",
    "cant_stay_home": "I can't stay in my home",
    "lost_belongings": "I lost belongings, a car, or other property",
    "lost_work": "I lost work or income because of the disaster",
    "medical_costs": "I have disaster-related medical or dental costs",
    "funeral_costs": "Someone in my household died because of the disaster",
    "child_care": "I need help paying for child care",
    "emotional_distress": "I am struggling emotionally",
    "legal_help": "I need legal help (papers, landlord, contractor, insurance)",
    "lost_documents": "I lost my ID or important papers",
    "business_damaged": "My business was damaged",
    "appeal": "FEMA denied me, or I disagree with a decision",
    "recovery_plan": "I need help planning my recovery",
    "scam_concern": "Someone contacted me about disaster aid and I'm not sure it's real",
}

# Offline need detection. Suggestions only: the person confirms before any
# program list is built from them. With Azure OpenAI configured the same
# confirmation step applies to the model's suggestions.
_NEED_CUES: dict[str, list[str]] = {
    "home_damaged": [r"\bdamag", r"\broof\b", r"flood(?:ed|ing)? (?:my |the |our )?(?:house|home|basement)",
                     r"water (?:in|inside|got into)", r"\bdestroy", r"collaps", r"\bmold\b", r"tree (?:fell|on)"],
    "cant_stay_home": [r"can'?t (?:stay|live|go back)", r"cannot (?:stay|live|go back)", r"nowhere to (?:stay|go|live)",
                       r"\bhomeless\b", r"\bshelter\b", r"\bhotel\b", r"\bdisplaced\b", r"\bevacuated\b"],
    "lost_belongings": [r"lost everything", r"\bbelongings\b", r"\bfurniture\b", r"\bclothes\b", r"\bappliances?\b",
                        r"\b(?:my |our )?(?:car|truck|vehicle) (?:was |is )?(?:flooded|damaged|destroyed|gone)"],
    "lost_work": [r"lost (?:my )?(?:job|work|income)", r"can'?t work", r"cannot work", r"\bunemploy",
                  r"no (?:income|paycheck)", r"(?:shop|store|workplace) (?:closed|destroyed)"],
    "medical_costs": [r"\bmedical\b", r"\bdoctor\b", r"hospital bill", r"\bmedicine\b", r"\bdental\b", r"\bprescription"],
    "funeral_costs": [r"\bfuneral\b", r"\bdied\b", r"passed away", r"\bburial\b"],
    "child_care": [r"child ?care", r"\bdaycare\b", r"\bbabysit"],
    "emotional_distress": [r"\bstress", r"\banxi", r"can'?t sleep", r"\bscared\b", r"\bdepress", r"\boverwhelm",
                           r"\bgrie(?:f|ving)"],
    "legal_help": [r"\blawyer\b", r"\blegal\b", r"\blandlord\b", r"\bcontractor\b", r"\bwill\b", r"power of attorney",
                   r"insurance (?:claim|company|denied)"],
    "lost_documents": [r"lost (?:my )?(?:id|papers|documents|license|passport|birth certificate)",
                       r"(?:papers|documents) (?:were )?(?:destroyed|lost|washed away)"],
    "business_damaged": [r"\bmy (?:business|shop|store|restaurant|farm)\b"],
    "appeal": [r"\bdenied\b", r"\bappeal", r"\bineligible\b", r"not eligible", r"\brejected\b"],
    "recovery_plan": [r"don'?t know (?:where|what) to (?:start|do)", r"\bno idea\b", r"help me plan"],
    "scam_concern": [r"\bscam", r"asked (?:me )?for (?:money|a fee|my bank)", r"\bsuspicious\b", r"\bfake\b",
                     r"someone (?:called|texted|emailed|came)"],
}
_NEED_RE = {k: [re.compile(p, re.I) for p in v] for k, v in _NEED_CUES.items()}


# Official names a survivor must be able to say to a FEMA Helpline operator
# exactly as FEMA says them. Locked as entities so neither the simplifier
# ("assistance" -> "help") nor a translator can rewrite them. Found the hard
# way: without this list the status line read "Individual Help area".
PROPER_NAMES = [
    "Individual Assistance", "Individuals and Households Program", "Public Assistance",
    "Housing Assistance", "Other Needs Assistance", "Home Repair or Replacement Assistance",
    "Continued Temporary Housing Assistance", "Disaster Unemployment Assistance",
    "Disaster Legal Services", "Disaster Case Management", "Disaster Distress Helpline",
    "Disaster Recovery Center", "FEMA Helpline", "Helpline",
    "Investigations and Inspections Division", "National Center for Disaster Fraud",
    "Office of Inspector General", "Office of the Inspector General",
    "American Bar Association", "Young Lawyers' Division", "Young Lawyers Division",
    "Small Business Administration", "Department of Labor", "Department of Homeland Security",
    "Substance Abuse and Mental Health Services Administration", "988 Suicide & Crisis Lifeline",
    "FEMA", "SBA", "DHS", "SAMHSA", "IHP", "DUA", "DLS", "OIG",
]


# Words the simplifier may not swap in this product, because they are how the
# agencies name things. Distinct from PROPER_NAMES: these stay translatable
# (FEMA's own Spanish pages say "asistencia"), they just may not be
# plain-languaged into a synonym a Helpline operator would not recognise.
VOCABULARY_OF_RECORD = frozenset({"assistance", "eligible", "registration", "inspection",
                                  "appeal", "application", "applicants", "disaster"})


def suggest_needs(redacted_text: str | None) -> list[str]:
    if not redacted_text:
        return []
    return [need for need, pats in _NEED_RE.items() if any(p.search(redacted_text) for p in pats)]


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

_CATALOG: dict | None = None


def _catalog() -> dict:
    global _CATALOG
    if _CATALOG is None:
        with sources.PROGRAMS_PATH.open(encoding="utf-8") as fh:
            _CATALOG = json.load(fh)
    return _CATALOG


def _rule(rule_id: str) -> sources.Citation | None:
    spec = _catalog().get("rules", {}).get(rule_id)
    return sources.locate(spec["doc"], spec["quote"]) if spec else None


# ---------------------------------------------------------------------------
# Declarations
# ---------------------------------------------------------------------------

RECENT_DAYS = 365


def _parse(ts: str | None) -> dt.datetime | None:
    if not ts:
        return None
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _human_date(iso: str | None) -> str:
    # Built by hand: "%-d" is a glibc extension and fails on Windows.
    if not iso:
        return "an unknown date"
    d = dt.date.fromisoformat(iso[:10])
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def assess(fips: str, now: dt.datetime) -> dict:
    """Declarations for a county, as they stood at `now`."""
    all_decl = [d for d in fema.declarations_for_county(fips)
                if (_parse(d.declaration_date) or now) <= now]
    rows = []
    for d in all_decl:
        rows.append({"declaration": d, "window": fema.registration_window(d, now)})

    def recent(r) -> bool:
        return (now - _parse(r["declaration"].declaration_date)).days <= RECENT_DAYS

    live_ia = [r for r in rows if r["window"]["state"] in ("open", "late")]
    recent_rows = [r for r in rows if recent(r)]
    primary = (live_ia[0] if live_ia else (recent_rows[0] if recent_rows else (rows[0] if rows else None)))
    return {
        "primary": primary,
        "live_ia": live_ia,
        "recent": recent_rows,
        "history": rows[:8],
        "major_disaster_recent": any(r["declaration"].declaration_type == "DR" for r in recent_rows),
        "any_recent": bool(recent_rows),
    }


def status_statement(county: str, a: dict) -> tuple[str, str]:
    """The one sentence that answers 'is there help here, and how long do I have'.
    Built from OpenFEMA fields only. Returns (code, sentence)."""
    p = a["primary"]
    if p is None:
        return "none", (f"FEMA's data shows no disaster declaration for {county} since 2015.")
    d, w = p["declaration"], p["window"]
    name = f"{d.title} ({d.declaration_string})"
    if w["state"] == "open":
        return "ia_open", (f"{county} is in the Individual Assistance area for {name}. "
                           f"FEMA's recorded deadline to apply is {_human_date(w['deadline'])}: "
                           f"{w['days_left']} days left.")
    if w["state"] == "late":
        return "ia_late", (f"{county} is in the Individual Assistance area for {name}. "
                           f"The deadline to apply, {_human_date(w['deadline'])}, has passed, "
                           f"but late applications are accepted until {_human_date(w['late_until'])} "
                           f"if you explain the reason for the delay: {w['late_days_left']} days left.")
    if w["state"] == "closed":
        return "ia_closed", (f"{county} was in the Individual Assistance area for {name}. "
                             f"The deadline to apply, including the late period, has passed.")
    if w["state"] == "unknown":
        return "ia_unknown", (f"{county} is in the Individual Assistance area for {name}. "
                              f"FEMA's data does not list a deadline to apply.")
    return "no_ia", (f"{county} is in the declared area for {name}, but that declaration does not "
                     f"include Individual Assistance for households here.")


# ---------------------------------------------------------------------------
# Programs
# ---------------------------------------------------------------------------

AVAILABILITY_TEXT = {
    "likely": "Your county is in the declared area for this help. FEMA decides who qualifies after you apply.",
    "late": "The deadline has passed, but late applications are still accepted if you explain the delay.",
    "closed": "The time to apply for this declaration has passed.",
    "check": "This help may be available here, but FEMA's declaration data cannot confirm it. Ask the FEMA Helpline.",
    "always": "Available now.",
    "unavailable": "Not part of a current declaration for your county.",
}


def availability(gate: str, a: dict) -> str:
    p = a["primary"]
    state = p["window"]["state"] if p else "none"
    if gate == "always":
        return "always"
    if gate == "individual_assistance":
        return {"open": "likely", "late": "late", "unknown": "likely",
                "closed": "closed"}.get(state, "unavailable")
    if gate == "major_disaster":
        return "check" if a["major_disaster_recent"] else "unavailable"
    if gate == "any_declaration":
        return "check" if a["any_recent"] else "unavailable"
    return "unavailable"


# ---------------------------------------------------------------------------
# The request
# ---------------------------------------------------------------------------


def navigate(
    location: str,
    needs: list[str] | None = None,
    text: str | None = None,
    danger_now: bool = False,
    lang: str = "en",
    target_grade: float | None = None,
    pick_fips: str | None = None,
    now: dt.datetime | None = None,
    corrupt_fn=None,
) -> dict:
    t0 = time.perf_counter()
    now = now or dt.datetime.now(dt.timezone.utc)
    target_grade = config.TARGET_READING_GRADE if target_grade is None else target_grade
    needs = [n for n in (needs or []) if n in NEEDS]

    # 1. Privacy first: nothing downstream ever sees an identifier.
    red = privacy.redact(text)

    # 2. Escalation floor, before location - a person in danger does not need
    #    to finish the form first.
    triggers_rules = esc.rule_triggers(red.text)
    triggers_flags = esc.flag_triggers(danger_now=danger_now, needs=needs)
    # Redacted text only. The model can add escalations, never remove them.
    triggers_model = esc.model_triggers(red.text)

    # 3. Where.
    where = areas.resolve(location, pick_fips=pick_fips)
    suggestions = [n for n in suggest_needs(red.text) if n not in needs]

    base = {
        "render_id": uuid.uuid4().hex[:16],
        "language": lang,
        "language_name": config.SUPPORTED_LANGUAGES.get(lang, {}).get("name", "English"),
        "text_direction": config.SUPPORTED_LANGUAGES.get(lang, {}).get("dir", "ltr"),
        "created_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "location": where.to_dict(),
        "privacy": red.to_dict(),
        "needs": needs,
        "suggested_needs": [{"code": n, "label": NEEDS[n]} for n in suggestions],
        "suggestion_engine": "local-keyword-cues (confirmation required)",
    }

    if where.county_fips is None:
        # Cannot place the person. Escalation still stands: someone typing
        # "trapped" into an unresolvable box still gets 911.
        e = esc.merge(triggers_rules, triggers_flags, triggers_model)
        base.update({
            "needs_location_choice": where.ambiguous,
            "escalation": e.to_dict(),
            "segments": [],
            "programs": [],
        })
        return base

    county = where.county_name
    a = assess(where.county_fips, now)
    code, statement = status_statement(county, a)

    # System-raised escalations: situations the data cannot resolve.
    system: list[esc.Trigger] = []
    reported_damage = bool({"home_damaged", "cant_stay_home"} & set(needs + suggestions))
    if code in ("none", "no_ia") and reported_damage:
        system.append(esc.system_trigger(
            "damage_without_ia",
            "You reported damage, but FEMA's data shows no Individual Assistance for your county. "
            "A person can tell you whether that is changing and what else exists."))
    if code == "ia_closed" and reported_damage:
        system.append(esc.system_trigger(
            "deadline_passed", "The recorded deadline has passed. A person can confirm whether anything is still open."))

    e_pre = esc.merge(triggers_rules, triggers_flags, triggers_model, system)

    # 4. Build segments. Everything the person will read goes through the
    #    same verify-and-abstain pipeline as the alert product.
    segs: list[Segment] = []

    def add(role: str, text_: str, required: bool = False, **meta) -> Segment:
        s = Segment(id=f"s{len(segs) + 1}", role=role, source_text=text_,
                    required_action=required, meta=meta)
        segs.append(s)
        return s

    for t in sorted(e_pre.triggers, key=lambda t: -esc.RANK[t.level]):
        add("escalation", t.reason, required=True, trigger=t.id, level=t.level)
    for ch in e_pre.to_dict()["channels"]:
        if ch.get("verified"):
            add("channel", ch["citation"]["quote"], required=True, channel=ch["id"],
                label=ch["label"], citation=ch["citation"])

    add("status", statement, status_code=code, basis="OpenFEMA DisasterDeclarationsSummaries")
    p = a["primary"]
    if p and p["window"]["state"] in ("open", "late", "closed", "unknown"):
        add("notice", p["window"]["caveat"] or "", kind="deadline_caveat")
        if p["window"]["state"] == "late":
            for rid in ("late_registration", "late_registration_reason"):
                c = _rule(rid)
                if c:
                    add("claim", c.quote, required=True, rule=rid, citation=c.to_dict())

    raw_programs = {p["id"]: p for p in _catalog()["programs"]}
    programs_out = []
    for prog in sources.load_programs():
        if needs and not set(prog.needs) & set(needs):
            continue
        # An unavailable program is still listed, with its reason, so a person
        # sees why it is not offered rather than wondering if it was forgotten.
        avail = availability(prog.gate, a)
        name_seg = add("program_name", prog.name, program=prog.id)
        status_seg = add("program_status", AVAILABILITY_TEXT[avail], program=prog.id, availability=avail)
        claim_ids = []
        if avail != "unavailable":
            for claim in prog.claims:
                s = add("claim", claim.citation.quote, required=(claim.kind in ("how_to_apply", "deadline", "contact")),
                        program=prog.id, claim_kind=claim.kind, citation=claim.citation.to_dict())
                claim_ids.append(s.id)
        programs_out.append({
            "id": prog.id, "name": prog.name, "agency": prog.agency,
            "availability": avail, "gate": prog.gate, "gate_note": prog.gate_note,
            "status_independent": bool(raw_programs[prog.id].get("status_independent")),
            "name_segment": name_seg.id, "status_segment": status_seg.id,
            "claim_segments": claim_ids, "dropped_claims": prog.dropped,
        })

    immigration = any(t.id == "immigration" for t in e_pre.triggers)
    for note in _catalog().get("status_notes", []):
        c = sources.locate(note["doc"], note["quote"])
        if c:
            add("status_note", c.quote, emphasized=immigration, citation=c.to_dict())

    c = _rule("language_need")
    if c:
        add("notice", c.quote, kind="language_need", citation=c.to_dict())

    for w in _catalog().get("fraud_warnings", []):
        c = sources.locate(w["doc"], w["quote"])
        if c:
            add("fraud", c.quote, required=(w["kind"] == "report"), citation=c.to_dict())

    if red.any:
        add("notice", red.notice(), kind="privacy")

    # 5. The pipeline.
    gaz = ent.Gazetteer.load()
    event_names = [r["declaration"].title for r in a["history"]]
    gaz.add_many([county] + event_names + PROPER_NAMES)
    pr = run_pipeline(segs, lang, target_grade, gaz, corrupt_fn=corrupt_fn,
                      protect_terms=VOCABULARY_OF_RECORD,
                      trusted_source_passthrough=True)

    abstained = [s for s in segs if s.status == "verbatim_abstained"]
    if abstained and lang != "en":
        system.append(esc.system_trigger(
            "translation_withheld",
            "Part of this page is shown only in English because its translation could not be verified.",
            ["fema_helpline"]))
    e = esc.merge(triggers_rules, triggers_flags, triggers_model, system)

    seg_dicts = [s.to_dict() for s in segs]
    return {
        **base,
        "needs_location_choice": False,
        "county": {"fips": where.county_fips, "name": county},
        "status_code": code,
        "declarations": {
            "primary": _decl_dict(a["primary"]),
            "other_live": [_decl_dict(r) for r in a["live_ia"][1:]],
            "history": [_decl_dict(r) for r in a["history"]],
            "source": _decl_source(),
        },
        "escalation": e.to_dict(),
        "programs": programs_out,
        "segments": seg_dicts,
        "segment_count": len(segs),
        "abstained_count": len(abstained),
        "abstention_reasons": sorted({s.reason for s in abstained if s.reason}),
        "transform_chain": pr["chain"],
        "corrupted_segments": pr["corrupted_ids"],
        "providers": pr["registry"].describe(),
        "provider_notes": pr["registry"].notes,
        "entities_locked": pr["total_entities"],
        "document_coverage": pr["doc_coverage"].to_dict(),
        "sources_used": _sources_used(seg_dicts),
        "elapsed_ms": int((time.perf_counter() - t0) * 1000),
    }


def _decl_dict(row: dict | None) -> dict | None:
    if not row:
        return None
    return {**row["declaration"].to_dict(), "window": row["window"]}


def _decl_source() -> dict:
    snap = fema.load_snapshot("declarations_va") or {}
    return {"dataset": "OpenFEMA DisasterDeclarationsSummaries v2", "sha256": snap.get("sha256"),
            "fetched_at": snap.get("fetched_at"), "rows": snap.get("row_count")}


def _sources_used(seg_dicts: list[dict]) -> list[dict]:
    used: dict[str, dict] = {}
    corpus = sources.corpus()
    for s in seg_dicts:
        cite = (s.get("meta") or {}).get("citation")
        if cite and cite["doc_id"] not in used and cite["doc_id"] in corpus:
            used[cite["doc_id"]] = corpus[cite["doc_id"]].summary()
    return list(used.values())
