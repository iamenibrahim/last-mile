"""The impact number: ACS B16004 x the alert archive.

Brief section 7. One afternoon of public-data work, and it is the entire
Economic Value & Societal Impact quarter.

    python -m grounded_eval.impact --state 51

DEVIATION FROM THE BRIEF, and it needs saying on Day 1: the brief lists
api.census.gov as "free, no key". That is no longer true - every dataset and
every year now 302s to missing_key.html. Signup is free and instant at
https://api.census.gov/data/key_signup.html; set CENSUS_API_KEY.

Without a key this module reports that the figure is unavailable. It does not
estimate, interpolate, or fall back to a remembered number. An impact figure on
a slide with no data behind it is worse than no figure, and a judge who asks
where it came from will find out.

TWO NUMBERS, NOT ONE. County-level attribution is an upper bound: an alert
polygon covering three blocks of a county is credited with the whole county's
LEP population. The area-weighted estimate multiplies each county's LEP count
by the share of that county's area the polygon actually covers. The truth is
between them, closer to the weighted figure, and both are reported with the
method named. Population is not uniform over area, so the weighting is itself
an approximation - stated, not hidden.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from grounded import config, geo, ingest  # noqa: E402

ACS_YEAR = os.environ.get("ACS_YEAR", "2023")
GROUP = "B16004"
GROUP_META = f"https://api.census.gov/data/{ACS_YEAR}/acs/acs5/groups/{GROUP}.json"
ACS_DATA = f"https://api.census.gov/data/{ACS_YEAR}/acs/acs5"
CACHE_PATH = config.DATA_DIR / f"acs_{GROUP}_{ACS_YEAR}.json"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

# "Speak English less than very well" = well + not well + not at all.
LEP_LEVELS = ('Speak English "well"', 'Speak English "not well"', 'Speak English "not at all"')


def lep_variables() -> tuple[list[str], str]:
    """Derive the LEP variable list from the published labels.

    Keyless, and it means the selection is auditable rather than a hardcoded
    list of 36 variable numbers that nobody can check.
    """
    r = httpx.get(GROUP_META, timeout=60, follow_redirects=True)
    r.raise_for_status()
    variables = r.json()["variables"]
    chosen = []
    for name, meta in variables.items():
        if not name.endswith("E"):
            continue
        label = meta.get("label", "")
        if any(label.rstrip(":").endswith(level) for level in LEP_LEVELS):
            chosen.append(name)
    chosen.sort()
    return chosen, f"{GROUP} {ACS_YEAR} ACS 5-year, levels {LEP_LEVELS}"


def fetch_acs(state_fips: str, variables: list[str], api_key: str) -> dict[str, dict]:
    """County-level LEP counts. The API caps `get` at 50 variables per call."""
    out: dict[str, dict] = defaultdict(lambda: {"lep": 0, "name": None})
    for i in range(0, len(variables), 45):
        chunk = variables[i : i + 45]
        params = {
            "get": "NAME," + ",".join(chunk),
            "for": "county:*",
            "in": f"state:{state_fips}",
            "key": api_key,
        }
        r = httpx.get(ACS_DATA, params=params, timeout=90, follow_redirects=True)
        r.raise_for_status()
        rows = r.json()
        header = rows[0]
        for row in rows[1:]:
            rec = dict(zip(header, row))
            fips = f"{rec['state']}{rec['county']}"
            out[fips]["name"] = rec["NAME"]
            for var in chunk:
                try:
                    value = int(rec[var])
                except (TypeError, ValueError):
                    continue
                if value > 0:  # ACS uses negatives as annotation flags
                    out[fips]["lep"] += value
    return dict(out)


def load_acs(state_fips: str) -> tuple[dict[str, dict], dict]:
    """Cached ACS counts, or fetch them if a key is present."""
    if CACHE_PATH.exists():
        with CACHE_PATH.open(encoding="utf-8") as fh:
            blob = json.load(fh)
        if blob.get("state_fips") == state_fips:
            return blob["counties"], blob["meta"]

    api_key = os.environ.get("CENSUS_API_KEY")
    if not api_key:
        raise RuntimeError(
            "CENSUS_API_KEY is not set and there is no cached ACS extract.\n"
            "api.census.gov now requires a key for every dataset and year.\n"
            "Free, instant signup: https://api.census.gov/data/key_signup.html\n"
            "No impact figure is produced without real data."
        )

    variables, provenance = lep_variables()
    counties = fetch_acs(state_fips, variables, api_key)
    meta = {
        "source": f"ACS 5-year {ACS_YEAR}, table {GROUP}",
        "variables_used": len(variables),
        "selection_rule": provenance,
        "fetched_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "definition": 'residents aged 5+ who speak a language other than English at '
                      'home and report speaking English less than "very well"',
    }
    CACHE_PATH.write_text(
        json.dumps({"state_fips": state_fips, "counties": counties, "meta": meta},
                   indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return counties, meta


# ---------------------------------------------------------------------------
# Alert -> county
# ---------------------------------------------------------------------------

SAME_RE = re.compile(r"^0(\d{5})$")


def alert_counties(feature: dict, state_fips: str) -> list[str]:
    """County FIPS codes an alert covers, from its own SAME geocodes."""
    same = ((feature.get("properties") or {}).get("geocode") or {}).get("SAME") or []
    out = []
    for code in same:
        m = SAME_RE.match(str(code))
        if m and m.group(1).startswith(state_fips):
            out.append(m.group(1))
    return out


def county_geometry(ugc: str) -> dict | None:
    """NWS county zone polygon. Keyless, and cached by api.geo."""
    return geo.fetch_zone_geometry(f"{config.NWS_BASE}/zones/county/{ugc}")


def area_share(alert_geom: dict | None, county_geom: dict | None) -> float | None:
    """Share of a county's area covered by the alert polygon."""
    if not alert_geom or not county_geom:
        return None
    try:
        from shapely.geometry import shape
        from shapely.ops import transform as shp_transform

        county = shape(county_geom)
        alert = shape(alert_geom)
        lat0 = county.centroid.y
        project = geo._km_projector(lat0)
        county_km = shp_transform(project, county)
        alert_km = shp_transform(project, alert)
        if county_km.area <= 0:
            return None
        if not county_km.is_valid:
            county_km = county_km.buffer(0)
        if not alert_km.is_valid:
            alert_km = alert_km.buffer(0)
        return min(1.0, county_km.intersection(alert_km).area / county_km.area)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="51", help="state FIPS, 51 = Virginia")
    ap.add_argument("--no-area-weight", action="store_true",
                    help="skip the area-weighted estimate (it fetches county polygons)")
    args = ap.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        counties, meta = load_acs(args.state)
    except RuntimeError as exc:
        print(f"IMPACT FIGURE UNAVAILABLE\n\n{exc}")
        RESULTS_DIR.joinpath("impact.json").write_text(
            json.dumps(
                {
                    "available": False,
                    "reason": str(exc),
                    "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return 2

    alerts = ingest.load_cached()
    state_alerts = [f for f in alerts if alert_counties(f, args.state)]
    print(f"ACS: {len(counties)} counties, {sum(c['lep'] for c in counties.values()):,} LEP residents")
    print(f"corpus: {len(alerts)} cached alerts, {len(state_alerts)} covering state {args.state}")

    covered: set[str] = set()
    alerts_per_county: dict[str, int] = defaultdict(int)
    weighted_person_alerts = 0.0
    county_person_alerts = 0
    weighting_resolved = 0
    weighting_missing = 0

    for feature in state_alerts:
        fipses = alert_counties(feature, args.state)
        alert_geom, _ = geo.alert_geometry(feature, allow_zone_fallback=False)
        ugcs = ((feature.get("properties") or {}).get("geocode") or {}).get("UGC") or []
        ugc_by_fips = {}
        for ugc in ugcs:
            m = re.match(r"^([A-Z]{2})C(\d{3})$", str(ugc))
            if m:
                ugc_by_fips[f"{args.state}{m.group(2)}"] = ugc

        for fips in fipses:
            covered.add(fips)
            alerts_per_county[fips] += 1
            lep = counties.get(fips, {}).get("lep", 0)
            county_person_alerts += lep

            if args.no_area_weight or not alert_geom:
                weighted_person_alerts += lep
                weighting_missing += 1
                continue
            ugc = ugc_by_fips.get(fips)
            share = area_share(alert_geom, county_geometry(ugc)) if ugc else None
            if share is None:
                weighted_person_alerts += lep
                weighting_missing += 1
            else:
                weighted_person_alerts += lep * share
                weighting_resolved += 1

    distinct_lep = sum(counties.get(f, {}).get("lep", 0) for f in covered)
    total_state_lep = sum(c["lep"] for c in counties.values())

    report = {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "available": True,
        "state_fips": args.state,
        "acs": meta,
        "corpus": {
            "cached_alerts": len(alerts),
            "alerts_in_state": len(state_alerts),
            "window": "whatever data/cached_alerts holds; the NWS public archive "
                      "window is roughly one week, so this is NOT a 12-month figure "
                      "unless the cache has been accumulated over 12 months",
        },
        "counties_covered": len(covered),
        "counties_in_state": len(counties),
        "lep_in_covered_counties": distinct_lep,
        "lep_statewide": total_state_lep,
        "person_alerts": {
            "county_attribution": county_person_alerts,
            "area_weighted": round(weighted_person_alerts),
            "method": {
                "county_attribution": "UPPER BOUND. Every alert is credited with the "
                                      "full LEP population of every county it touches, "
                                      "however small the polygon.",
                "area_weighted": "CENTRAL ESTIMATE. Each county's LEP count is scaled "
                                 "by the share of that county's area the alert polygon "
                                 "covers. Population is not uniform over area, so this "
                                 "is an approximation, not a correction.",
                "weighting_resolved": weighting_resolved,
                "weighting_fell_back_to_full_county": weighting_missing,
            },
        },
        "top_counties": sorted(
            (
                {
                    "fips": f,
                    "name": counties.get(f, {}).get("name"),
                    "lep": counties.get(f, {}).get("lep", 0),
                    "alerts": alerts_per_county[f],
                }
                for f in covered
            ),
            key=lambda r: r["lep"] * r["alerts"],
            reverse=True,
        )[:15],
        "headline": None,
        "caveats": [
            "All of these residents received English-only alert text. That is the "
            "finding; the arithmetic above is only its size.",
            "The corpus is whatever has been cached. The NWS public archive window "
            "is about a week, so a 12-month claim requires 12 months of accumulated "
            "fetches - do not extrapolate from a week and call it a year.",
            "LEP is self-reported English-speaking ability from the ACS, aggregated "
            "at county level. It is not a count of people who cannot read an alert.",
            "An alert covering part of a county is credited against that county; see "
            "the two methods above for the spread.",
        ],
    }

    report["headline"] = (
        f"{len(state_alerts)} NWS alerts in this corpus covered Virginia polygons in "
        f"{len(covered)} counties, home to an estimated {distinct_lep:,} residents who "
        f'speak English less than "very well" - all of whom received English-only text.'
    )

    out = RESULTS_DIR / "impact.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print(report["headline"])
    print()
    print(f"  person-alerts, county attribution (upper bound): {county_person_alerts:,}")
    print(f"  person-alerts, area weighted (central estimate): {round(weighted_person_alerts):,}")
    print(f"  statewide LEP population for reference:          {total_state_lep:,}")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
