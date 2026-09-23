"""FastAPI surface. One process, no microservices (brief section 5).

    uvicorn api.main:app --reload --port 8000

Endpoints
    GET  /api/health                provider wiring, corpus state, honest mode flags
    GET  /api/alerts                cached corpus (the demo never reads live data)
    GET  /api/alerts/active         live NWS fetch, explicitly opt-in
    GET  /api/alerts/{id}           one alert, raw CAP
    POST /api/locate                address -> which cached alerts contain it
    POST /api/render                the full transform for one alert + address
    GET  /api/audio/{render_id}     spoken output
    POST /api/verify                manifest validation + source side by side
    GET  /api/corpus/stats          instruction-coverage finding (brief section 7)
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import actions, config, fema, geo, ingest, manifest as mf, speech, transform
from .providers.base import get_registry
from .store import get_store

app = FastAPI(
    title="Last-Mile Alert",
    version="0.1.0",
    description=(
        "Transforms authoritative NWS emergency alerts into plain, translated, "
        "household-relative, provenance-carrying renderings. This system never "
        "originates an alert; it only transforms authoritative ones."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_ALERT_CACHE: dict[str, dict] = {}


def _corpus() -> dict[str, dict]:
    if not _ALERT_CACHE:
        for f in ingest.load_cached():
            _ALERT_CACHE[ingest.alert_id(f)] = f
    return _ALERT_CACHE


@app.on_event("startup")
def _startup() -> None:
    corpus = _corpus()
    if corpus:
        ingest.load_into_store(corpus.values())


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class LocateRequest(BaseModel):
    address: str = Field(..., min_length=3)
    include_zone_fallback: bool = True


class RenderRequest(BaseModel):
    alert_id: str
    address: str | None = None
    lang: str = "en"
    target_grade: float | None = None
    with_audio: bool = False
    # Demo/eval only: replay the alert as at a given instant so a cached alert
    # does not read as expired. Never changes the source, only the clock.
    as_of: str | None = None
    corrupt: str | None = None
    corrupt_segment: str | None = None


class VerifyRequest(BaseModel):
    manifest: dict[str, Any]
    rendered_segments: list[dict[str, Any]] | None = None


class AssistRequest(BaseModel):
    """The navigator request. `text` and `location` are used for this request
    only and never stored; see api/privacy.py and api/areas.py."""

    location: str = Field("", max_length=300)
    needs: list[str] = Field(default_factory=list)
    text: str | None = Field(None, max_length=4000)
    danger_now: bool = False
    lang: str = "en"
    target_grade: float | None = None
    pick_fips: str | None = None
    as_of: str | None = None
    with_audio: bool = False
    corrupt: str | None = None
    corrupt_segment: str | None = None


# ---------------------------------------------------------------------------
# Health and corpus
# ---------------------------------------------------------------------------


@app.get("/api/health")
def health() -> dict:
    registry = get_registry()
    corpus = _corpus()
    with_instruction = sum(
        1 for f in corpus.values() if (f["properties"].get("instruction") or "").strip()
    )
    return {
        "ok": True,
        "offline_mode": config.OFFLINE,
        "providers": registry.describe(),
        "provider_notes": registry.notes,
        "azure_live": {
            k: v.startswith("azure") or v.startswith("key vault")
            for k, v in registry.notes.items()
        },
        "semantic_embeddings": bool(getattr(registry.embedder, "semantic", False)),
        "llm_judge": bool(getattr(registry.judge, "llm_backed", False)),
        "degraded_note": (
            None
            if registry.describe()["translator"].startswith("azure")
            else "Running on local fallback providers. Output is produced by "
                 "deterministic stubs, not Azure models, and is labelled as such "
                 "everywhere it appears."
        ),
        "corpus": {
            "cached_alerts": len(corpus),
            "with_instruction": with_instruction,
            "gazetteer": config.GAZETTEER_PATH.exists(),
        },
        "languages": config.SUPPORTED_LANGUAGES,
        "never_originates_alerts": True,
    }


@app.get("/api/corpus/stats")
def corpus_stats() -> dict:
    """The instruction-coverage finding (brief section 7): reported, not scored."""
    corpus = list(_corpus().values())
    rows = []
    by_event: dict[str, dict] = {}
    for f in corpus:
        props = f["properties"]
        cov = actions.describe_coverage(props.get("instruction"))
        event = props.get("event", "?")
        bucket = by_event.setdefault(event, {"n": 0, "with_instruction": 0, "with_geometry": 0})
        bucket["n"] += 1
        bucket["with_instruction"] += int(cov["has_instruction"])
        bucket["with_geometry"] += int(bool(f.get("geometry")))
        rows.append({"alert_id": ingest.alert_id(f), "event": event, **cov,
                     "has_geometry": bool(f.get("geometry"))})

    n = len(corpus) or 1
    return {
        "alerts": len(corpus),
        "with_instruction": sum(1 for r in rows if r["has_instruction"]),
        "pct_with_instruction": round(sum(1 for r in rows if r["has_instruction"]) / n, 4),
        "with_geometry": sum(1 for r in rows if r["has_geometry"]),
        "pct_with_geometry": round(sum(1 for r in rows if r["has_geometry"]) / n, 4),
        "by_event": by_event,
        "note": (
            "Alerts without an instruction field get no action list. This system "
            "does not infer actions, so the share of alerts carrying instructions "
            "is a property of the source feed and is reported as a finding."
        ),
    }


@app.get("/api/alerts")
def list_alerts(limit: int = 200, area: str | None = None,
                with_geometry: bool = False) -> dict:
    out = []
    for aid, f in _corpus().items():
        props = f["properties"]
        if with_geometry and not f.get("geometry"):
            continue
        if area and area.upper() not in (props.get("areaDesc") or "").upper() \
                and area.upper() not in (props.get("senderName") or "").upper():
            continue
        out.append(
            {
                "id": aid,
                "event": props.get("event"),
                "headline": props.get("headline"),
                "areaDesc": props.get("areaDesc"),
                "senderName": props.get("senderName"),
                "severity": props.get("severity"),
                "urgency": props.get("urgency"),
                "certainty": props.get("certainty"),
                "sent": props.get("sent"),
                "onset": props.get("onset"),
                "expires": props.get("expires"),
                "has_geometry": bool(f.get("geometry")),
                "has_instruction": bool((props.get("instruction") or "").strip()),
                "sha256": (f.get("_provenance") or {}).get("sha256"),
            }
        )
    out.sort(key=lambda r: r["sent"] or "", reverse=True)
    return {"count": len(out), "alerts": out[:limit],
            "source": "data/cached_alerts (real NWS products; none synthetic)"}


@app.get("/api/alerts/active")
def active_alerts(area: str = "VA") -> dict:
    """Live fetch. The demo does not use this - see brief section 12."""
    try:
        features = ingest.fetch_active(area)
    except Exception as exc:
        raise HTTPException(502, f"NWS fetch failed: {type(exc).__name__}: {exc}")
    store = get_store()
    for f in features:
        aid = ingest.alert_id(f)
        _ALERT_CACHE[aid] = f
        store.put_alert(aid, f)
    return {"count": len(features), "area": area,
            "alerts": [{"id": ingest.alert_id(f), "event": f["properties"].get("event"),
                        "areaDesc": f["properties"].get("areaDesc")} for f in features]}


@app.get("/api/alerts/{alert_id:path}")
def get_alert(alert_id: str) -> dict:
    feature = _corpus().get(alert_id) or get_store().get_alert(alert_id)
    if not feature:
        raise HTTPException(404, "alert not found in cache or store")
    return feature


# ---------------------------------------------------------------------------
# Locate
# ---------------------------------------------------------------------------


@app.post("/api/locate")
def locate(req: LocateRequest) -> dict:
    located = geo.geocode(req.address)
    if located is None:
        raise HTTPException(
            422,
            "Address could not be geocoded. Try a full street address including "
            "city and state.",
        )

    matches, near = [], []
    for aid, feature in _corpus().items():
        geometry, basis = geo.alert_geometry(
            feature, allow_zone_fallback=req.include_zone_fallback
        )
        if not geometry:
            continue
        rel = geo.relate_point(located.lat, located.lon, geometry, basis=basis)
        props = feature["properties"]
        row = {
            "id": aid,
            "event": props.get("event"),
            "headline": props.get("headline"),
            "areaDesc": props.get("areaDesc"),
            "senderName": props.get("senderName"),
            "sent": props.get("sent"),
            "expires": props.get("expires"),
            "has_instruction": bool((props.get("instruction") or "").strip()),
            "relation": rel.to_dict(),
        }
        if rel.status == "inside":
            matches.append(row)
        elif rel.status == "near_edge":
            near.append(row)

    matches.sort(key=lambda r: r["sent"] or "", reverse=True)
    near.sort(key=lambda r: r["relation"]["distance_km"] or 1e9)
    return {
        "geocode": located.to_dict(),
        "inside": matches,
        "near_edge": near,
        "counts": {"inside": len(matches), "near_edge": len(near),
                   "searched": len(_corpus())},
        "geocode_caveat": (
            "Matched to a town centre, not a street address - the inside/outside "
            "answer describes the town, not your house."
            if located.confidence == "place_centroid" else None
        ),
    }


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


def _parse_as_of(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(422, f"as_of is not an ISO-8601 timestamp: {value!r}")
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


@app.post("/api/render")
def render(req: RenderRequest) -> dict:
    feature = _corpus().get(req.alert_id) or get_store().get_alert(req.alert_id)
    if not feature:
        raise HTTPException(404, "alert not found")
    if req.lang != "en" and req.lang not in config.SUPPORTED_LANGUAGES:
        raise HTTPException(
            422,
            f"language {req.lang!r} is not one of the demo targets "
            f"{sorted(config.SUPPORTED_LANGUAGES)} (brief section 11 caps this at 4)",
        )

    corrupt_fn = None
    corruption_meta = None
    if req.corrupt:
        from eval import corrupt as C

        if req.corrupt not in C.CLASSES:
            raise HTTPException(422, f"unknown corruption class; expected one of {C.CLASSES}")
        baseline = transform.transform_alert(feature, lang=req.lang,
                                             target_grade=req.target_grade)
        locked = {s["id"]: s.get("entities", []) for s in baseline["segments"]}
        target = req.corrupt_segment
        if not target:
            eligible = C.eligible_segments(req.corrupt, baseline["segments"])
            if not eligible:
                raise HTTPException(
                    422, f"no segment in this alert is eligible for {req.corrupt!r}"
                )
            target = eligible[0]
        corrupt_fn, corruption_meta = C.make_corruptor(req.corrupt, target, locked)

    result = transform.transform_alert(
        feature, lang=req.lang, target_grade=req.target_grade, corrupt_fn=corrupt_fn
    )

    household = None
    if req.address:
        household = transform.household_context(
            feature, req.address, now=_parse_as_of(req.as_of)
        )
        result["household"] = household

    result["manifest"] = mf.build_signed(result, feature)
    result["source"] = {
        "event": feature["properties"].get("event"),
        "headline": feature["properties"].get("headline"),
        "areaDesc": feature["properties"].get("areaDesc"),
        "senderName": feature["properties"].get("senderName"),
        "description": feature["properties"].get("description"),
        "instruction": feature["properties"].get("instruction"),
        "sent": feature["properties"].get("sent"),
    }
    if corruption_meta:
        result["corruption"] = {
            **corruption_meta,
            "warning": (
                "ADVERSARIAL TEST INPUT. This render was deliberately damaged to "
                "demonstrate the verifier. It is not a production artifact and its "
                "manifest is marked accordingly."
            ),
        }

    if req.with_audio:
        result["audio"] = speech.synthesize_for_render(result, household)

    get_store().put_render(result["render_id"], result)
    return result


@app.get("/api/audio/{render_id}")
def audio(render_id: str, lang: str = Query("en")) -> Response:
    got = get_store().get_audio(render_id, lang)
    if not got:
        raise HTTPException(404, "no audio for this render; request it with with_audio=true")
    blob, mime = got
    return Response(content=blob, media_type=mime,
                    headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------


@app.post("/api/verify")
def verify_manifest(req: VerifyRequest) -> dict:
    manifest_doc = req.manifest
    cap_id = (manifest_doc.get("source") or {}).get("cap_id")
    feature = _corpus().get(cap_id) or (get_store().get_alert(cap_id) if cap_id else None)
    report = mf.validate(manifest_doc, feature=feature, rendered_segments=req.rendered_segments)
    out = report.to_dict()
    out["source_available_locally"] = feature is not None
    if feature is None:
        out["note"] = (
            "The source alert is not in this instance's cache, so the source hash "
            "was not recomputed. Signature and internal consistency were still checked."
        )
    return out


@app.get("/api/verify/example")
def verify_example() -> dict:
    """A known-good manifest, so the verify path can be demoed without a render."""
    corpus = _corpus()
    if not corpus:
        raise HTTPException(503, "no cached alerts; run scripts/fetch_corpus.py")
    feature = next(
        (f for f in corpus.values() if (f["properties"].get("instruction") or "").strip()),
        next(iter(corpus.values())),
    )
    result = transform.transform_alert(feature, lang="en")
    return mf.build_signed(result, feature)


# ---------------------------------------------------------------------------
# Disaster Assistance Navigator
# ---------------------------------------------------------------------------


@app.get("/api/assist/needs")
def assist_needs() -> dict:
    from . import navigator

    return {"needs": [{"code": k, "label": v} for k, v in navigator.NEEDS.items()]}


@app.get("/api/assist/counties")
def assist_counties() -> dict:
    from . import areas

    return {"counties": areas.all_counties(),
            "source": "Census 2023 Gazetteer, Virginia county-equivalents (95 counties, 38 cities)"}


# Corrupting a fraud warning is the demo that matters for this track: "will
# never charge applicants" becoming "will charge applicants" is the failure a
# scammer would most like to see shipped.
_CORRUPT_ROLE_PREFERENCE = ["fraud", "escalation", "channel", "claim", "status"]


@app.post("/api/assist")
def assist(req: AssistRequest) -> dict:
    from . import navigator

    if req.lang != "en" and req.lang not in config.SUPPORTED_LANGUAGES:
        raise HTTPException(422, f"language {req.lang!r} is not one of {sorted(config.SUPPORTED_LANGUAGES)}")
    now = _parse_as_of(req.as_of)
    kwargs = dict(location=req.location, needs=req.needs, text=req.text, danger_now=req.danger_now,
                  lang=req.lang, target_grade=req.target_grade, pick_fips=req.pick_fips, now=now)

    corrupt_fn = corruption_meta = None
    if req.corrupt:
        from eval import corrupt as C

        if req.corrupt not in C.CLASSES:
            raise HTTPException(422, f"unknown corruption class; expected one of {C.CLASSES}")
        baseline = navigator.navigate(**kwargs)
        segs = baseline.get("segments", [])
        role = {s["id"]: s["role"] for s in segs}
        eligible = C.eligible_segments(req.corrupt, segs)
        if req.corrupt in ("hallucinate_instruction", "drop_instruction"):
            eligible = [s["id"] for s in segs if s["role"] in ("claim", "fraud", "channel")]
        eligible.sort(key=lambda sid: _CORRUPT_ROLE_PREFERENCE.index(role[sid])
                      if role[sid] in _CORRUPT_ROLE_PREFERENCE else 99)
        target = req.corrupt_segment or (eligible[0] if eligible else None)
        if not target:
            raise HTTPException(422, f"no segment on this page is eligible for {req.corrupt!r}")
        locked = {s["id"]: s.get("entities", []) for s in segs}
        corrupt_fn, corruption_meta = C.make_corruptor(req.corrupt, target, locked)

    result = navigator.navigate(**kwargs, corrupt_fn=corrupt_fn)
    if result.get("segments"):
        result["manifest"] = mf.build_navigator_signed(result)
    if corruption_meta:
        result["corruption"] = {**corruption_meta, "warning": (
            "ADVERSARIAL TEST INPUT. This page was deliberately damaged to demonstrate "
            "the verifier. It is not a production artifact and its manifest says so.")}
    if req.with_audio and result.get("segments"):
        result["audio"] = speech.synthesize_script(
            result["render_id"], req.lang, speech.navigator_script(result))
    # Deliberately no store.put_render: a navigator page is returned, not kept.
    return result


@app.get("/api/assist/impact")
def assist_impact() -> dict:
    """The impact figure that needs no Census key: Helene registrations in VA."""
    summary = fema.registrations_summary(4831)
    if not summary:
        raise HTTPException(503, "no DR-4831 snapshot; run scripts/fetch_fema.py")
    return summary


# ---------------------------------------------------------------------------
# Static front end (no build step)
#
# Mounted at the root and registered LAST, so it acts as the fallback: Starlette
# matches routes in registration order, and every /api route above is already
# claimed by the time a request reaches this mount.
# ---------------------------------------------------------------------------

if config.WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(config.WEB_DIR), html=True), name="web")
else:  # pragma: no cover

    @app.get("/")
    def root() -> Any:
        return JSONResponse({"ok": True, "see": "/docs"})
