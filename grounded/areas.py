"""Resolve whatever a person types into a Virginia county-equivalent.

Disaster declarations are made county by county (and independent city by
independent city - Virginia has 95 counties and 38 independent cities, 133
county-equivalents in all). So the navigator needs a county, and nothing finer.
It accepts, from least to most revealing:

    a county or city name   "Smyth", "Galax", "Roanoke city"
    a ZIP code              "24370"
    a street address        only if the person chooses to give one

and keeps only the resulting county FIPS code.

AMBIGUITY IS ASKED, NEVER GUESSED. 35% of Virginia ZIP codes cross a county
line (Census 2020 ZCTA-to-county relationship file), and "Roanoke" names both
a county and an independent city. Eligibility can differ across that line, so
when the input maps to more than one county-equivalent the resolver returns
the candidates and the person picks. Picking the largest overlap would be
right most of the time and wrong in exactly the cases where it matters.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict

import httpx

from . import config

AREAS_PATH = config.DATA_DIR / "va_areas.json"
STATE_FIPS = "51"

_AREAS: dict | None = None


def _areas() -> dict:
    global _AREAS
    if _AREAS is None:
        if AREAS_PATH.exists():
            with AREAS_PATH.open(encoding="utf-8") as fh:
                _AREAS = json.load(fh)
        else:
            _AREAS = {"counties": {}, "zcta_to_county": {}}
    return _AREAS


def county_name(fips: str) -> str:
    return _areas()["counties"].get(fips, fips)


@dataclass
class Candidate:
    county_fips: str
    county_name: str
    share: float | None = None  # share of the ZIP's land area in this county

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Resolution:
    input_kind: str  # "zip" | "county" | "address" | "fips" | "unknown"
    county_fips: str | None
    county_name: str | None
    ambiguous: bool = False
    candidates: list[Candidate] = field(default_factory=list)
    source: str = ""
    note: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["candidates"] = [c.to_dict() for c in self.candidates]
        d["retained"] = "county FIPS only; the text you typed is not stored"
        return d


def _norm(s: str) -> str:
    s = s.lower().replace(",", " ")
    s = re.sub(r"\b(?:va|virginia)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _by_name(text: str) -> list[Candidate]:
    q = _norm(text)
    if not q:
        return []
    exact, loose = [], []
    for fips, name in _areas()["counties"].items():
        n = _norm(name)                              # "smyth county" / "galax city"
        base = re.sub(r"\s+(county|city)$", "", n)  # "smyth" / "galax"
        if q == n:
            exact.append(Candidate(fips, name))
        elif q == base:
            loose.append(Candidate(fips, name))
    return exact or loose


def _by_zip(zip5: str) -> list[Candidate]:
    rows = _areas()["zcta_to_county"].get(zip5, [])
    total = sum(r["land_part"] for r in rows) or 1
    out = [Candidate(r["county_fips"], county_name(r["county_fips"]), round(r["land_part"] / total, 3))
           for r in rows]
    return sorted(out, key=lambda c: -(c.share or 0))


def _by_address(address: str) -> Candidate | None:
    """Census geocoder, geographies endpoint: address -> county GEOID."""
    if config.OFFLINE:
        return None
    try:
        r = httpx.get(
            "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress",
            params={"address": address, "benchmark": "Public_AR_Current",
                    "vintage": "Current_Current", "format": "json", "layers": "Counties"},
            timeout=25,
        )
        r.raise_for_status()
        matches = r.json().get("result", {}).get("addressMatches", [])
    except Exception:
        return None
    if not matches:
        return None
    counties = matches[0].get("geographies", {}).get("Counties", [])
    if not counties:
        return None
    geoid = counties[0]["GEOID"]
    return Candidate(geoid, county_name(geoid))


def resolve(text: str | None, pick_fips: str | None = None) -> Resolution:
    """Map free input to one county-equivalent, or to a list to choose from.

    `pick_fips` is the person's answer to an earlier ambiguous result; it is
    honoured only if it was one of the candidates, so a stale or forged pick
    cannot land someone in a county their input never pointed at.
    """
    raw = (text or "").strip()
    if not raw:
        return Resolution("unknown", None, None, note="Enter a county, city, or ZIP code.")

    if re.fullmatch(r"51\d{3}", raw) and raw in _areas()["counties"]:
        return Resolution("fips", raw, county_name(raw), source="FIPS code")

    zip_m = re.fullmatch(r"(\d{5})(?:-\d{4})?", raw)
    if zip_m:
        cands = _by_zip(zip_m.group(1))
        source = "Census 2020 ZCTA-to-county relationship file"
        if not cands:
            return Resolution("zip", None, None, source=source,
                              note="That ZIP code is not in Virginia's Census ZIP list.")
        return _settle("zip", cands, pick_fips, source,
                       "This ZIP code crosses a county line. Which county do you live in?")

    cands = _by_name(raw)
    if cands:
        return _settle("county", cands, pick_fips, "Census 2023 Gazetteer county-equivalents",
                       "That name matches more than one place. Which one do you mean?")

    # Only now treat it as an address. Nothing about it is kept beyond the county.
    hit = _by_address(raw if "va" in raw.lower() or "virginia" in raw.lower() else raw + ", VA")
    if hit and hit.county_fips.startswith(STATE_FIPS):
        return Resolution("address", hit.county_fips, hit.county_name, source="Census geocoder")
    if hit:
        return Resolution("address", None, None, source="Census geocoder",
                          note=f"That address is in {hit.county_name}, outside Virginia.")
    return Resolution("unknown", None, None,
                      note="We could not match that. Try your county name or ZIP code.")


def _settle(kind: str, cands: list[Candidate], pick: str | None, source: str,
            question: str) -> Resolution:
    if pick and any(c.county_fips == pick for c in cands):
        c = next(c for c in cands if c.county_fips == pick)
        return Resolution(kind, c.county_fips, c.county_name, source=source,
                          candidates=cands, note="You chose this county.")
    if len(cands) == 1:
        return Resolution(kind, cands[0].county_fips, cands[0].county_name, source=source,
                          candidates=cands)
    return Resolution(kind, None, None, ambiguous=True, candidates=cands, source=source,
                      note=question)


def all_counties() -> list[dict]:
    return [{"fips": f, "name": n} for f, n in sorted(_areas()["counties"].items(), key=lambda x: x[1])]
