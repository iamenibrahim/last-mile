"""NWS fetch, canonicalisation and hashing.

Brief section 3.2. The hash is the anchor of the whole provenance claim, so
what exactly gets hashed has to be pinned down and reproducible:

    CANONICAL FORM = RFC 8785-style JSON of the CAP GeoJSON *feature* -
    keys sorted recursively, no insignificant whitespace, UTF-8, non-ASCII
    left unescaped - with our own `_provenance` block excluded.

That means the hash is stable across refetches, across pretty-printing, and
across our own annotations, and anyone with the same feature can recompute it.

HONESTY BOUNDARY (brief section 3.2, INVARIANT): api.weather.gov does not hand
us an end-to-end verifiable digital signature over the CAP product. The trust
anchor is TLS to the NWS origin plus our own signature over what we fetched.
`transport` and `trust_anchor` in the provenance block say so in the artifact
itself, so the limitation travels with the data instead of living only on a
slide. C2PA Content Credentials are the real fix and are out of scope here.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import httpx

from . import config
from .store import get_store

TIMEOUT = httpx.Timeout(30.0, connect=10.0)
TRUST_ANCHOR_NOTE = (
    "TLS to api.weather.gov + our own signature over the fetched bytes. "
    "NWS CAP products retrieved via this API are not individually signed in a "
    "way this system can verify end to end; this is not a verified NWS signature."
)


def _headers() -> dict[str, str]:
    return {"User-Agent": config.NWS_USER_AGENT, "Accept": "application/geo+json"}


def canonicalize(feature: dict) -> bytes:
    """Deterministic byte form of a CAP feature. See module docstring."""
    stripped = {k: v for k, v in feature.items() if k != "_provenance"}
    return json.dumps(
        stripped, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_of(feature: dict) -> str:
    return hashlib.sha256(canonicalize(feature)).hexdigest()


def _utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def annotate(feature: dict, source_url: str, fetched_at: str | None = None) -> dict:
    """Attach the provenance block. Idempotent: hashing ignores the block."""
    props = feature.get("properties", {})
    feature["_provenance"] = {
        "url": props.get("@id") or feature.get("id") or source_url,
        "collection_url": source_url,
        "cap_id": props.get("id") or feature.get("id"),
        "sha256": sha256_of(feature),
        "sender": props.get("senderName"),
        "sent": props.get("sent"),
        "fetched_at": fetched_at or _utcnow(),
        "transport": "TLS to api.weather.gov",
        "trust_anchor": TRUST_ANCHOR_NOTE,
        "canonicalization": "json sorted-keys, no whitespace, utf-8, _provenance excluded",
    }
    return feature


def fetch_active(area: str = "VA") -> list[dict]:
    # An empty area means "everywhere"; the API rejects a bare `area=`.
    url = f"{config.NWS_BASE}/alerts/active" + (f"?area={area}" if area else "")
    r = httpx.get(url, headers=_headers(), timeout=TIMEOUT, follow_redirects=True)
    r.raise_for_status()
    fetched = _utcnow()
    return [annotate(f, url, fetched) for f in r.json().get("features", [])]


def fetch_window(area: str = "VA", start: str | None = None, end: str | None = None,
                 limit: int = 500) -> list[dict]:
    """Archive query. The public window is short - roughly the last week - which
    is why data/cached_alerts exists (brief section 12)."""
    url = f"{config.NWS_BASE}/alerts?area={area}&limit={limit}"
    if start:
        url += f"&start={start}"
    if end:
        url += f"&end={end}"
    r = httpx.get(url, headers=_headers(), timeout=TIMEOUT, follow_redirects=True)
    r.raise_for_status()
    fetched = _utcnow()
    return [annotate(f, url, fetched) for f in r.json().get("features", [])]


def alert_id(feature: dict) -> str:
    return (
        feature.get("properties", {}).get("id")
        or feature.get("id")
        or feature.get("_provenance", {}).get("sha256", "unknown")
    )


def save_cached(features: Iterable[dict], directory: Path | None = None) -> int:
    """Write one JSON file per alert into data/cached_alerts.

    Demoing against live data you do not control is the single most avoidable
    hackathon failure (brief section 12). Everything the demo touches is read
    from disk.
    """
    directory = directory or config.CACHED_ALERTS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in features:
        aid = alert_id(f)
        safe = aid.replace(":", "_").replace("/", "_").replace(".", "_")[-120:]
        path = directory / f"{safe}.json"
        path.write_text(json.dumps(f, ensure_ascii=False, indent=2), encoding="utf-8")
        n += 1
    return n


def load_cached(directory: Path | None = None) -> list[dict]:
    directory = directory or config.CACHED_ALERTS_DIR
    if not directory.exists():
        return []
    out: list[dict] = []
    for path in sorted(directory.glob("*.json")):
        try:
            with path.open(encoding="utf-8") as fh:
                doc = json.load(fh)
            if isinstance(doc, dict) and doc.get("properties"):
                out.append(doc)
        except Exception:
            continue
    out.sort(key=lambda f: f.get("properties", {}).get("sent") or "", reverse=True)
    return out


def verify_cached_hashes(features: Iterable[dict]) -> list[tuple[str, bool]]:
    """Recompute every cached hash. A False here means the file was edited."""
    results = []
    for f in features:
        recorded = f.get("_provenance", {}).get("sha256")
        results.append((alert_id(f), recorded == sha256_of(f)))
    return results


def load_into_store(features: Iterable[dict] | None = None) -> int:
    """Populate the alert store from cache (default) or a supplied list."""
    store = get_store()
    feats = list(features) if features is not None else load_cached()
    for f in feats:
        if "_provenance" not in f:
            annotate(f, "local-cache")
        store.put_alert(alert_id(f), f)
    return len(feats)


# ---------------------------------------------------------------------------
# Timer-triggered ingest body (Azure Functions entry point lives in api/function_app.py)
# ---------------------------------------------------------------------------


def ingest_once(area: str = "VA", persist_cache: bool = False) -> dict[str, Any]:
    """Fetch active alerts, hash, store. Safe to call on a timer."""
    started = _utcnow()
    try:
        features = fetch_active(area)
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "started": started}
    store = get_store()
    for f in features:
        store.put_alert(alert_id(f), f)
    if persist_cache and features:
        save_cached(features)
    return {
        "ok": True,
        "started": started,
        "finished": _utcnow(),
        "area": area,
        "count": len(features),
        "ids": [alert_id(f) for f in features][:25],
    }
