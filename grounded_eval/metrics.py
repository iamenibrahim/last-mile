"""The evaluation harness. Real public data, real numbers, stated limits.

Brief section 7. Run this on Day 4 and put what it prints in the deck.

    python -m grounded_eval.metrics --lang en --limit 40
    python -m grounded_eval.metrics --lang es --limit 25 --ablate

WHAT IS AND IS NOT MEASURED HERE, stated up front because the whole value of
this harness is that its numbers survive a hostile question:

  * Flesch-Kincaid is an English formula. It is reported for the English
    render, and for non-English targets it describes the simplified English the
    translation was made *from*. It says nothing about readability in Dari.
    Target-language readability needs native-speaker review and is not claimed.

  * chrF++ needs reference translations. There are none for these alerts, so
    what is reported is back-translation agreement - a proxy, labelled as a
    proxy everywhere it appears, never as a translation-quality score.

  * With no Azure credentials the embedder is a lexical bag-of-words stub and
    the judge is a rule-based floor. Numbers produced in that configuration
    measure the *plumbing*, not the models. The report prints which engines
    produced every figure.

  * Thresholds are tuned on this corpus and reported with the corpus size. A
    threshold tuned on 65 alerts is a threshold tuned on 65 alerts.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import textstat  # noqa: E402

from grounded import config, ingest, transform  # noqa: E402
from grounded import verify as vf  # noqa: E402
from grounded.providers.base import get_registry  # noqa: E402
from grounded_eval import corrupt as C  # noqa: E402

RESULTS_DIR = Path(__file__).resolve().parent / "results"
THRESHOLDS_PATH = Path(__file__).resolve().parent / "thresholds.json"
THRESHOLD_GRID = [round(x / 100, 2) for x in range(30, 100, 2)]
MAX_FALSE_ABSTENTION = 0.10  # brief section 7 target


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


def _strip_locked(text: str) -> str:
    """Remove the spans entity locking protects, for the floor measurement."""
    from grounded import entities as ent

    locked = ent.lock(text, ent.Gazetteer.load())
    return re.sub(r"\s+", " ", ent.SENTINEL_RE.sub(" ", locked.masked)).strip()


@dataclass
class SegmentRecord:
    alert_id: str
    segment_id: str
    role: str
    required_action: bool
    status: str
    reason: str | None
    has_free_text: bool
    scores: dict = field(default_factory=dict)
    passed: dict = field(default_factory=dict)

    def status_at(self, semantic_threshold: float) -> bool:
        """Would this segment pass, if the fidelity threshold were t?"""
        for name, ok in self.passed.items():
            if name == "semantic_fidelity":
                score = self.scores.get("semantic_fidelity")
                if score is None:
                    continue  # nothing to paraphrase; check abstains from opining
                if score < semantic_threshold:
                    return False
            elif not ok:
                return False
        return True


def _records_from_render(render: dict) -> list[SegmentRecord]:
    out = []
    for seg in render["segments"]:
        scores, passed = {}, {}
        for c in seg.get("checks", []):
            scores[c["name"]] = c["score"]
            passed[c["name"]] = c["passed"]
        out.append(
            SegmentRecord(
                alert_id=render["alert_id"],
                segment_id=seg["id"],
                role=seg["role"],
                required_action=seg.get("required_action", False),
                status=seg["status"],
                reason=seg.get("reason"),
                has_free_text=scores.get("semantic_fidelity") is not None,
                scores=scores,
                passed=passed,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Clean run
# ---------------------------------------------------------------------------


def run_clean(alerts: list[dict], lang: str, lock_entities: bool = True):
    records: list[SegmentRecord] = []
    latencies: list[float] = []
    readability_rows: list[dict] = []
    entity_rows: list[dict] = []
    coverage_rows: list[dict] = []

    for feature in alerts:
        props = feature["properties"]
        t0 = time.perf_counter()
        render = transform.transform_alert(feature, lang=lang, lock_entities=lock_entities)
        latencies.append((time.perf_counter() - t0) * 1000)
        records += _records_from_render(render)

        source_text = " ".join(
            x for x in [props.get("description"), props.get("instruction")] if x
        ).strip()
        # The English we would publish: simplified English for an English
        # render, and the simplified English the translation was made from
        # otherwise. FK on target-language text would be meaningless.
        output_text = " ".join(
            s["output_text"] for s in render["segments"] if s["status"] == "translated_verified"
        ).strip()
        if lang != "en":
            output_text = " ".join(
                s.get("output_text", "") for s in render["segments"]
            ).strip()

        if len(source_text.split()) >= 25 and len(output_text.split()) >= 15:
            # The achievable floor. Flesch-Kincaid counts syllables, and county,
            # town and river names are polysyllabic by nature - "Withlacoochee",
            # "Pittsylvania", "Middle Fork Holston River". Those are locked
            # entities: they must survive verbatim, so no simplifier can spend
            # them. Measuring FK with the locked spans removed separates "text
            # we failed to simplify" from "syllables the source requires us to
            # keep", which is the difference between a missed target and a
            # target that was never reachable.
            stripped = _strip_locked(output_text)
            row = {
                "alert_id": render["alert_id"],
                "event": props.get("event"),
                "source_fk": round(textstat.flesch_kincaid_grade(source_text), 2),
                "output_fk": round(textstat.flesch_kincaid_grade(output_text), 2),
                "source_dale_chall": round(textstat.dale_chall_readability_score(source_text), 2),
                "output_dale_chall": round(textstat.dale_chall_readability_score(output_text), 2),
            }
            if len(stripped.split()) >= 15:
                row["output_fk_excluding_locked_entities"] = round(
                    textstat.flesch_kincaid_grade(stripped), 2
                )
            readability_rows.append(row)

        entity_rows.append(
            {
                "alert_id": render["alert_id"],
                "locked": render["entities_locked"],
                "integrity_failures": sum(
                    1
                    for s in render["segments"]
                    for c in s.get("checks", [])
                    if c["name"] == "entity_integrity" and not c["passed"]
                ),
            }
        )
        coverage_rows.append(
            {
                "alert_id": render["alert_id"],
                "event": props.get("event"),
                "has_instruction": not render["no_instructions_in_source"],
                "required_actions": sum(1 for s in render["steps"] if s.get("required_action")),
                "document_coverage": render["document_coverage"]["score"],
            }
        )

    return {
        "records": records,
        "latencies_ms": latencies,
        "readability": readability_rows,
        "entities": entity_rows,
        "coverage": coverage_rows,
    }


# ---------------------------------------------------------------------------
# Corruption run
# ---------------------------------------------------------------------------


def run_corruptions(alerts: list[dict], lang: str, classes=C.CLASSES,
                    max_targets_per_class: int = 2, lock_entities: bool = True,
                    seed: int = 7):
    """Damage one segment per run, record whether that segment abstained."""
    results: list[dict] = []
    for feature in alerts:
        baseline = transform.transform_alert(feature, lang=lang, lock_entities=lock_entities)
        by_id = {s["id"]: s for s in baseline["segments"]}
        locked_by_segment = {s["id"]: s.get("entities", []) for s in baseline["segments"]}

        for cls in classes:
            targets = C.eligible_segments(cls, baseline["segments"])[:max_targets_per_class]
            for target in targets:
                fn, record = C.make_corruptor(
                    cls, target, locked_by_segment, seed=seed, masked=lock_entities
                )
                render = transform.transform_alert(
                    feature, lang=lang, corrupt_fn=fn, lock_entities=lock_entities
                )
                if not record["applied"]:
                    continue
                seg = next((s for s in render["segments"] if s["id"] == target), None)
                if seg is None:
                    continue
                scores, passed = {}, {}
                for c in seg.get("checks", []):
                    scores[c["name"]] = c["score"]
                    passed[c["name"]] = c["passed"]
                results.append(
                    {
                        "alert_id": render["alert_id"],
                        "segment_id": target,
                        "class": cls,
                        "role": by_id[target]["role"],
                        "caught": seg["status"] == "verbatim_abstained",
                        "caught_by": seg.get("reason"),
                        "scores": scores,
                        "passed": passed,
                        "note": record["note"],
                    }
                )
    return results


# ---------------------------------------------------------------------------
# Threshold tuning
# ---------------------------------------------------------------------------


def _caught_at(row: dict, threshold: float) -> bool:
    for name, ok in row["passed"].items():
        if name == "semantic_fidelity":
            score = row["scores"].get("semantic_fidelity")
            if score is None:
                continue
            if score < threshold:
                return True
        elif not ok:
            return True
    return False


def tune_threshold(clean: list[SegmentRecord], corrupted: list[dict],
                   max_false_abstention: float = MAX_FALSE_ABSTENTION) -> dict:
    """Highest recall subject to the false-abstention ceiling.

    Sweeping the threshold and recomputing from stored scores is equivalent to
    rerunning the pipeline at each threshold, and about a thousand times
    cheaper.
    """
    rows = []
    for t in THRESHOLD_GRID:
        clean_abstained = sum(1 for r in clean if not r.status_at(t))
        false_rate = clean_abstained / max(1, len(clean))
        caught = sum(1 for r in corrupted if _caught_at(r, t))
        recall = caught / max(1, len(corrupted))
        rows.append(
            {
                "threshold": t,
                "false_abstention_rate": round(false_rate, 4),
                "abstention_recall": round(recall, 4),
                "clean_segments": len(clean),
                "corrupted_segments": len(corrupted),
            }
        )

    feasible = [r for r in rows if r["false_abstention_rate"] <= max_false_abstention]
    if feasible:
        best = max(feasible, key=lambda r: (r["abstention_recall"], r["threshold"]))
        note = f"highest recall with false-abstention <= {max_false_abstention:.0%}"
    else:
        best = min(rows, key=lambda r: r["false_abstention_rate"])
        note = (
            f"NO threshold met the {max_false_abstention:.0%} false-abstention ceiling on this "
            f"corpus; reporting the lowest achievable false-abstention rate instead"
        )
    return {"sweep": rows, "chosen": best, "note": note}


# ---------------------------------------------------------------------------
# Per-class breakdown - the persuasive table (brief section 7)
# ---------------------------------------------------------------------------


def by_class(corrupted: list[dict], threshold: float) -> list[dict]:
    buckets: dict[str, list[dict]] = defaultdict(list)
    for r in corrupted:
        buckets[r["class"]].append(r)

    out = []
    for cls in C.CLASSES:
        rows = buckets.get(cls, [])
        if not rows:
            out.append({"class": cls, "n": 0, "recall": None, "caught_by": {}})
            continue
        caught = [r for r in rows if _caught_at(r, threshold)]
        attribution: dict[str, int] = defaultdict(int)
        for r in caught:
            # Same precedence the runtime uses, so the table's "caught by"
            # column matches the reason a reader would see on the page.
            for name in vf.CHECK_ORDER:
                ok = r["passed"].get(name, True)
                if name == "semantic_fidelity":
                    score = r["scores"].get("semantic_fidelity")
                    ok = True if score is None else score >= threshold
                if not ok:
                    attribution[name] += 1
                    break
        out.append(
            {
                "class": cls,
                "n": len(rows),
                "recall": round(len(caught) / len(rows), 4),
                "caught_by": dict(attribution),
            }
        )
    return out


# ---------------------------------------------------------------------------
# Translation quality proxy
# ---------------------------------------------------------------------------


def backtranslation_agreement(alerts: list[dict], lang: str, limit: int = 15) -> dict:
    """chrF++ between source English and back-translated English.

    A PROXY. Not a translation-quality score. Reported because no reference
    translations exist for these alerts (brief section 12 risk row), and
    labelled as a proxy at every point it is printed.
    """
    if lang == "en":
        return {"applicable": False, "reason": "no translation step for an English render"}
    try:
        from sacrebleu.metrics import CHRF
    except Exception as exc:
        return {"applicable": False, "reason": f"sacrebleu unavailable: {exc}"}

    chrf = CHRF(word_order=2)  # chrF++
    hyps, refs = [], []
    for feature in alerts[:limit]:
        render = transform.transform_alert(feature, lang=lang)
        for seg in render["segments"]:
            src = seg.get("source_text", "").strip()
            if len(src.split()) < 5:
                continue
            back = seg.get("output_text", "")
            if seg["status"] != "translated_verified":
                continue
            hyps.append(back)
            refs.append(src)
    if not hyps:
        return {"applicable": False, "reason": "no verified segments to score"}
    score = chrf.corpus_score(hyps, [refs])
    return {
        "applicable": True,
        "metric": "chrF++ (sacrebleu, word_order=2)",
        "kind": "back-translation agreement PROXY, not a reference-based score",
        "score": round(score.score, 2),
        "segments": len(hyps),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="en")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--max-targets", type=int, default=2)
    ap.add_argument("--ablate", action="store_true",
                    help="also run with entity locking disabled, to quantify what the lock buys")
    ap.add_argument("--max-false-abstention", type=float, default=MAX_FALSE_ABSTENTION)
    args = ap.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    registry = get_registry()

    alerts = [f for f in ingest.load_cached() if (f["properties"].get("description") or "").strip()]
    alerts = alerts[: args.limit]
    if not alerts:
        print("No cached alerts. Run scripts/fetch_corpus.py first.")
        return 1

    print(f"corpus: {len(alerts)} alerts | lang={args.lang}")
    print(f"engines: {json.dumps(registry.describe())}")
    semantic = bool(getattr(registry.embedder, "semantic", False))
    llm_judge = bool(getattr(registry.judge, "llm_backed", False))
    if not (semantic and llm_judge):
        print("NOTE: running with local stub engines - these numbers measure the pipeline, "
              "not the Azure models.")

    print("\n[1/4] clean run")
    clean = run_clean(alerts, args.lang)
    print(f"      {len(clean['records'])} segments")

    print("[2/4] corruption injection")
    corrupted = run_corruptions(alerts, args.lang, max_targets_per_class=args.max_targets)
    print(f"      {len(corrupted)} corrupted segments across {len(C.CLASSES)} classes")

    print("[3/4] threshold sweep")
    tuning = tune_threshold(clean["records"], corrupted, args.max_false_abstention)
    chosen = tuning["chosen"]
    print(f"      threshold={chosen['threshold']} "
          f"recall={chosen['abstention_recall']:.1%} "
          f"false-abstention={chosen['false_abstention_rate']:.1%}")
    print(f"      {tuning['note']}")

    print("[4/4] per-class breakdown")
    class_table = by_class(corrupted, chosen["threshold"])
    for row in class_table:
        r = "n/a" if row["recall"] is None else f"{row['recall']:.0%}"
        print(f"      {row['class']:26s} n={row['n']:4d}  recall={r:>5s}  {row['caught_by']}")

    ablation = None
    if args.ablate:
        print("\n[ablation] entity locking disabled")
        ab_clean = run_clean(alerts, args.lang, lock_entities=False)
        ab_corrupt = run_corruptions(alerts, args.lang, max_targets_per_class=args.max_targets,
                                     lock_entities=False)
        ab_table = by_class(ab_corrupt, chosen["threshold"])
        for row in ab_table:
            r = "n/a" if row["recall"] is None else f"{row['recall']:.0%}"
            print(f"      {row['class']:26s} n={row['n']:4d}  recall={r:>5s}")
        ablation = {"by_class": ab_table, "clean_segments": len(ab_clean["records"])}

    lat = sorted(clean["latencies_ms"])
    fk = clean["readability"]
    entity_failures = sum(r["integrity_failures"] for r in clean["entities"])
    entities_locked = sum(r["locked"] for r in clean["entities"])
    with_instruction = sum(1 for r in clean["coverage"] if r["has_instruction"])

    report = {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lang": args.lang,
        "corpus_size": len(alerts),
        "engines": registry.describe(),
        "engine_notes": registry.notes,
        "semantic_embeddings": semantic,
        "llm_judge": llm_judge,
        "readability": {
            "n": len(fk),
            "applies_to": (
                "the English render" if args.lang == "en"
                else "the simplified English the translation was made from; "
                     "Flesch-Kincaid is an English formula and says nothing about "
                     f"readability in {config.SUPPORTED_LANGUAGES.get(args.lang,{}).get('name',args.lang)}"
            ),
            "median_source_fk": round(statistics.median([r["source_fk"] for r in fk]), 2) if fk else None,
            "median_output_fk": round(statistics.median([r["output_fk"] for r in fk]), 2) if fk else None,
            "median_output_fk_excluding_locked_entities": (
                round(statistics.median(
                    [r["output_fk_excluding_locked_entities"] for r in fk
                     if "output_fk_excluding_locked_entities" in r]
                ), 2)
                if any("output_fk_excluding_locked_entities" in r for r in fk) else None
            ),
            "pct_at_or_below_target": (
                round(sum(1 for r in fk if r["output_fk"] <= config.TARGET_READING_GRADE) / len(fk), 4)
                if fk else None
            ),
            "pct_at_or_below_target_excluding_locked_entities": (
                round(sum(1 for r in fk
                          if r.get("output_fk_excluding_locked_entities", 99)
                          <= config.TARGET_READING_GRADE) / len(fk), 4)
                if fk else None
            ),
            "target_grade": config.TARGET_READING_GRADE,
            "finding": (
                "The brief assumed source alerts read at grade 11-13. On this corpus "
                "they do not: NWS already writes in short, hard-wrapped sentences with "
                "a controlled vocabulary, so the measured source grade is far lower. "
                "The reading-level gain is therefore real but modest, and the dominant "
                "barrier in the data is that the text is English-only, not that it is "
                "written above grade level. Reporting this rather than the assumed "
                "premise is the point of running the harness."
            ),
            "floor_note": (
                "County, town and river names are locked entities and are "
                "polysyllabic by nature, so they put a floor under Flesch-Kincaid "
                "that no simplifier can lower without breaking the safety guarantee. "
                "The 'excluding_locked_entities' figures show the score for the prose "
                "we actually control."
            ),
            "rows": fk,
        },
        "entity_preservation": {
            "entities_locked": entities_locked,
            "integrity_failures": entity_failures,
            "rate": 1.0 if entities_locked == 0 else round(1 - entity_failures / entities_locked, 6),
        },
        "abstention": {
            "chosen_threshold": chosen["threshold"],
            "recall": chosen["abstention_recall"],
            "false_abstention_rate": chosen["false_abstention_rate"],
            "note": tuning["note"],
            "sweep": tuning["sweep"],
            "by_class": class_table,
        },
        "ablation_no_entity_lock": ablation,
        "latency_ms": {
            "n": len(lat),
            "p50": round(statistics.median(lat), 1) if lat else None,
            "p95": round(lat[int(len(lat) * 0.95) - 1], 1) if len(lat) >= 2 else None,
            "max": round(max(lat), 1) if lat else None,
            "scope": "single alert, all segments, one language, local process; "
                     "excludes network fetch and TTS",
        },
        "instruction_coverage_finding": {
            "alerts": len(clean["coverage"]),
            "with_instruction": with_instruction,
            "pct_with_instruction": round(with_instruction / max(1, len(clean["coverage"])), 4),
            "note": "reported as a finding, not a score (brief section 7)",
        },
        "translation_quality": backtranslation_agreement(alerts, args.lang),
    }

    out_path = RESULTS_DIR / f"metrics_{args.lang}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out_path}")

    existing = {}
    if THRESHOLDS_PATH.exists():
        try:
            existing = json.loads(THRESHOLDS_PATH.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    existing[registry.embedder.name] = {
        "semantic_fidelity": chosen["threshold"],
        "tuned_on": {"corpus_size": len(alerts), "lang": args.lang,
                     "at": report["generated_at"],
                     "false_abstention_ceiling": args.max_false_abstention},
    }
    THRESHOLDS_PATH.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    print(f"wrote {THRESHOLDS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
