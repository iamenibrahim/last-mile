"""Geocoding, point-in-polygon, distance to the polygon edge, and timing.

Brief section 3.3: household-relative context comes from geometry, not
language. The model is never asked whether an address is in the warning area,
because the model would answer even when it should not. Shapely answers.

Distance method: lat/lon are projected to a local equirectangular frame in
kilometres (longitude scaled by cos(latitude) about the query point) before any
shapely call, so `distance` comes back in km directly. Over a county-sized
polygon at Virginia's latitude the error is well under a percent - far tighter
than the 5 km band it feeds - and it avoids a projection dependency.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import re
from dataclasses import dataclass, asdict

import httpx
from shapely.geometry import Point, shape
from shapely.ops import nearest_points, transform as shp_transform

from . import config

TIMEOUT = httpx.Timeout(20.0, connect=8.0)
ZONE_CACHE_DIR = config.DATA_DIR / "zone_geometry"

EARTH_KM_PER_DEG_LAT = 110.574
EARTH_KM_PER_DEG_LON = 111.320


@dataclass
class GeocodeResult:
    lat: float
    lon: float
    matched_address: str
    source: str
    confidence: str = "exact"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Relation:
    """Where a household sits relative to the warning polygon."""

    status: str  # "inside" | "near_edge" | "outside" | "unknown"
    distance_km: float | None
    inside: bool
    nearest_edge: tuple[float, float] | None
    basis: str  # what geometry answered: "alert_polygon" | "zone_polygon" | "none"
    detail: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.nearest_edge:
            d["nearest_edge"] = list(self.nearest_edge)
        return d


# ---------------------------------------------------------------------------
# Geocoding
# ---------------------------------------------------------------------------


def _census_geocode(address: str) -> GeocodeResult | None:
    params = {
        "address": address,
        "benchmark": "Public_AR_Current",
        "format": "json",
    }
    r = httpx.get(config.CENSUS_GEOCODER, params=params, timeout=TIMEOUT, follow_redirects=True)
    r.raise_for_status()
    matches = r.json().get("result", {}).get("addressMatches", [])
    if not matches:
        return None
    m = matches[0]
    return GeocodeResult(
        lat=float(m["coordinates"]["y"]),
        lon=float(m["coordinates"]["x"]),
        matched_address=m.get("matchedAddress", address),
        source="census-geocoder",
    )


def _azure_geocode(address: str) -> GeocodeResult | None:  # pragma: no cover - key path
    key = config.AZURE.maps_key
    if not key:
        return None
    r = httpx.get(
        "https://atlas.microsoft.com/search/address/json",
        params={"api-version": "1.0", "subscription-key": key, "query": address, "countrySet": "US"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    results = r.json().get("results", [])
    if not results:
        return None
    top = results[0]
    return GeocodeResult(
        lat=float(top["position"]["lat"]),
        lon=float(top["position"]["lon"]),
        matched_address=top.get("address", {}).get("freeformAddress", address),
        source="azure-maps",
    )


_PLACE_POINTS: dict[str, tuple[float, float]] | None = None


def _local_place_geocode(address: str) -> GeocodeResult | None:
    """Last resort: match a Virginia place name and return its centroid.

    Deliberately reports confidence="place_centroid" so the caller can say so
    in the UI. A town centroid is not an address and must never be presented as
    one - the inside/outside answer it produces is about the town, not the house.
    """
    global _PLACE_POINTS
    if _PLACE_POINTS is None:
        path = config.DATA_DIR / "va_place_points.json"
        _PLACE_POINTS = {}
        if path.exists():
            with path.open(encoding="utf-8") as fh:
                _PLACE_POINTS = {k: tuple(v) for k, v in json.load(fh)["points"].items()}
    if not _PLACE_POINTS:
        return None
    hay = address.lower()
    best = None
    for name, (lat, lon) in _PLACE_POINTS.items():
        if re.search(rf"(?<![\w']){re.escape(name.lower())}(?![\w'])", hay):
            if best is None or len(name) > len(best[0]):
                best = (name, lat, lon)
    if not best:
        return None
    return GeocodeResult(
        lat=best[1],
        lon=best[2],
        matched_address=f"{best[0]}, VA (town centre)",
        source="local-place-centroid",
        confidence="place_centroid",
    )


def geocode(address: str) -> GeocodeResult | None:
    """Azure Maps if configured, Census geocoder otherwise, local centroid last."""
    address = (address or "").strip()
    if not address:
        return None

    if not config.OFFLINE and config.AZURE.maps_key:
        try:  # pragma: no cover - key path
            got = _azure_geocode(address)
            if got:
                return got
        except Exception:
            pass

    if not config.OFFLINE:
        try:
            got = _census_geocode(address)
            if got:
                return got
        except Exception:
            pass

    return _local_place_geocode(address)


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


def _km_projector(lat0: float):
    """Return a lon/lat -> km,km function centred on lat0."""
    kx = EARTH_KM_PER_DEG_LON * math.cos(math.radians(lat0))
    ky = EARTH_KM_PER_DEG_LAT

    def fn(x, y, z=None):
        if z is None:
            return (x * kx, y * ky)
        return (x * kx, y * ky, z)

    return fn


def _unproject(x_km: float, y_km: float, lat0: float) -> tuple[float, float]:
    kx = EARTH_KM_PER_DEG_LON * math.cos(math.radians(lat0))
    return (x_km / kx, y_km / EARTH_KM_PER_DEG_LAT)


def relate_point(lat: float, lon: float, geometry: dict | None,
                 basis: str = "alert_polygon",
                 near_km: float | None = None) -> Relation:
    """Inside / within N km of the edge / outside, with the distance in km."""
    near_km = config.NEAR_EDGE_KM if near_km is None else near_km
    if not geometry:
        return Relation(
            status="unknown",
            distance_km=None,
            inside=False,
            nearest_edge=None,
            basis="none",
            detail="this alert carries no polygon; see affectedZones",
        )

    try:
        geom = shape(geometry)
    except Exception as exc:
        return Relation("unknown", None, False, None, "none", f"unparseable geometry: {exc}")

    project = _km_projector(lat)
    geom_km = shp_transform(project, geom)
    pt_km = Point(*project(lon, lat))

    inside = geom_km.contains(pt_km) or geom_km.touches(pt_km)
    boundary = geom_km.boundary
    try:
        _, near = nearest_points(pt_km, boundary)
        edge_lonlat = _unproject(near.x, near.y, lat)
        distance_km = pt_km.distance(near)
    except Exception:
        edge_lonlat = None
        distance_km = 0.0 if inside else pt_km.distance(geom_km)

    if inside:
        status = "inside"
        detail = f"inside the warning polygon, {distance_km:.1f} km from the nearest edge"
    elif distance_km <= near_km:
        status = "near_edge"
        detail = f"outside the polygon but {distance_km:.1f} km from its edge"
    else:
        status = "outside"
        detail = f"{distance_km:.1f} km outside the warning polygon"

    return Relation(
        status=status,
        distance_km=round(distance_km, 2),
        inside=inside,
        nearest_edge=edge_lonlat,
        basis=basis,
        detail=detail,
    )


# ---------------------------------------------------------------------------
# Zone geometry for alerts issued without a polygon
# ---------------------------------------------------------------------------


def fetch_zone_geometry(zone_url: str) -> dict | None:
    """Resolve an affectedZones URL to a polygon, cached on disk.

    A meaningful share of NWS products are zone-based with `geometry: null`.
    Without this, those alerts can answer "is my house in it?" only at county
    resolution - which is worth reporting as a finding, not papering over.
    """
    ZONE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    zone_id = zone_url.rstrip("/").split("/")[-1]
    cached = ZONE_CACHE_DIR / f"{zone_id}.json"
    if cached.exists():
        try:
            with cached.open(encoding="utf-8") as fh:
                return json.load(fh).get("geometry")
        except Exception:
            pass
    if config.OFFLINE:
        return None
    try:
        r = httpx.get(
            zone_url,
            headers={"User-Agent": config.NWS_USER_AGENT, "Accept": "application/geo+json"},
            timeout=TIMEOUT,
            follow_redirects=True,
        )
        r.raise_for_status()
        doc = r.json()
    except Exception:
        return None
    if doc.get("geometry"):
        cached.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return doc.get("geometry")


def alert_geometry(feature: dict, allow_zone_fallback: bool = True) -> tuple[dict | None, str]:
    """Best available geometry for an alert, and what it came from."""
    if feature.get("geometry"):
        return feature["geometry"], "alert_polygon"
    if not allow_zone_fallback:
        return None, "none"
    zones = (feature.get("properties") or {}).get("affectedZones") or []
    polys = []
    for z in zones[:12]:
        g = fetch_zone_geometry(z)
        if g:
            polys.append(g)
    if not polys:
        return None, "none"
    if len(polys) == 1:
        return polys[0], "zone_polygon"
    try:
        from shapely.ops import unary_union

        merged = unary_union([shape(g) for g in polys])
        return json.loads(json.dumps(merged.__geo_interface__)), "zone_polygon"
    except Exception:
        return polys[0], "zone_polygon"


# ---------------------------------------------------------------------------
# Timing
# ---------------------------------------------------------------------------


def _parse(ts: str | None) -> dt.datetime | None:
    if not ts:
        return None
    try:
        return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass
class Timing:
    onset: str | None
    effective: str | None
    expires: str | None
    ends: str | None
    seconds_to_onset: int | None
    seconds_to_expiry: int | None
    state: str  # "before_onset" | "active" | "expired" | "unknown"
    human: str

    def to_dict(self) -> dict:
        return asdict(self)


def timing(properties: dict, now: dt.datetime | None = None) -> Timing:
    """Time remaining, computed from onset/effective/expires (brief 3.3).

    `now` is injectable so the demo can be replayed against a cached alert at
    the moment it was live rather than showing every cached alert as expired.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    onset = _parse(properties.get("onset"))
    effective = _parse(properties.get("effective"))
    expires = _parse(properties.get("expires"))
    ends = _parse(properties.get("ends"))
    end = ends or expires

    start = onset or effective
    to_onset = int((start - now).total_seconds()) if start else None
    to_expiry = int((end - now).total_seconds()) if end else None

    if to_onset is not None and to_onset > 0:
        state = "before_onset"
        human = f"starts in {_humanise(to_onset)}"
    elif to_expiry is not None and to_expiry > 0:
        state = "active"
        human = f"ends in {_humanise(to_expiry)}"
    elif to_expiry is not None:
        state = "expired"
        human = f"ended {_humanise(-to_expiry)} ago"
    else:
        state = "unknown"
        human = "no timing in the source"

    return Timing(
        onset=properties.get("onset"),
        effective=properties.get("effective"),
        expires=properties.get("expires"),
        ends=properties.get("ends"),
        seconds_to_onset=to_onset,
        seconds_to_expiry=to_expiry,
        state=state,
        human=human,
    )


def _plural(n: int, unit: str) -> str:
    return f"{n} {unit}" if n == 1 else f"{n} {unit}s"


def _humanise(seconds: int) -> str:
    seconds = max(0, int(seconds))
    if seconds < 90:
        return _plural(seconds, "second")
    minutes = seconds // 60
    if minutes < 90:
        return _plural(minutes, "minute")
    hours = minutes // 60
    if hours < 48:
        rem = minutes % 60
        return _plural(hours, "hour") + (f" {_plural(rem, 'minute')}" if rem else "")
    return _plural(hours // 24, "day")


def polygon_bounds(geometry: dict | None) -> list[float] | None:
    if not geometry:
        return None
    try:
        minx, miny, maxx, maxy = shape(geometry).bounds
        return [minx, miny, maxx, maxy]
    except Exception:
        return None
