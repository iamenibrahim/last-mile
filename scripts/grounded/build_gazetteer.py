"""Build the Virginia gazetteer that feeds entity locking (brief section 3.1).

Three free sources, no keys:
  1. NWS zones for VA  - county and forecast-zone names, and they are exactly
     the names NWS itself writes into areaDesc, so precision is high.
  2. Census places      - incorporated places and CDPs in state FIPS 51.
  3. The cached corpus  - stream, creek and town names lifted out of real alert
     descriptions by the waterway pattern, which is how "Middle Fork Holston
     River" gets into the list without anyone typing it.

Output: data/gazetteer_va.json

    python scripts/build_gazetteer.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from grounded import config, ingest  # noqa: E402
from grounded.entities import PATTERNS  # noqa: E402

HEADERS = {"User-Agent": config.NWS_USER_AGENT, "Accept": "application/geo+json"}
STOPWORDS = {
    "The", "This", "That", "These", "Those", "Some", "Most", "Other", "Additional",
    "National", "Weather", "Service", "Flood", "Flash", "Warning", "Advisory",
    "Watch", "Statement", "Until", "Between", "Doppler", "Radar", "Emergency",
    "Management", "Turn", "Move", "Avoid", "Please", "Reports", "Hazard", "Source",
    "Impact", "Impacts", "What", "Where", "When", "Details", "County", "Counties",
    "City", "Cities", "Area", "Areas", "River", "Creek", "Run", "Branch", "Fork",
}


def nws_zones() -> set[str]:
    out: set[str] = set()
    for zone_type in ("county", "public"):
        url = f"{config.NWS_BASE}/zones?area=VA&type={zone_type}"
        try:
            r = httpx.get(url, headers=HEADERS, timeout=30, follow_redirects=True)
            r.raise_for_status()
            for f in r.json().get("features", []):
                name = (f.get("properties") or {}).get("name")
                if name:
                    # "Grayson" / "Southwest Virginia" / "Northern Virginia Blue Ridge"
                    out.add(name.strip())
                    for part in re.split(r"\s*/\s*", name):
                        if part.strip():
                            out.add(part.strip())
        except Exception as exc:
            print(f"  zones {zone_type}: FAILED {exc}")
    return out


# The Census *data* API (api.census.gov) now 302s to missing_key.html for every
# dataset and year, so the brief's "free, no key" note no longer holds there.
# The Gazetteer flat files are still open, and they carry centroids, which buys
# an offline geocoder fallback for free.
GAZ_PLACE_URL = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/{year}_Gazetteer/{year}_gaz_place_51.txt"
LSAD_SUFFIX = re.compile(
    r"\s+(town|city|village|CDP|borough|municipality|comunidad|zona urbana)$", re.I
)


def census_places() -> tuple[set[str], dict[str, tuple[float, float]]]:
    """Virginia places from the keyless Gazetteer file. Returns (names, centroids)."""
    names: set[str] = set()
    points: dict[str, tuple[float, float]] = {}
    for year in (2023, 2022, 2021):
        try:
            r = httpx.get(GAZ_PLACE_URL.format(year=year), timeout=60, follow_redirects=True)
            r.raise_for_status()
        except Exception as exc:
            print(f"  gazetteer {year}: {exc}")
            continue
        lines = r.text.splitlines()
        header = [h.strip() for h in lines[0].split("\t")]
        idx = {h: i for i, h in enumerate(header)}
        for line in lines[1:]:
            cells = line.split("\t")
            if len(cells) < len(header):
                continue
            raw = cells[idx["NAME"]].strip()
            name = LSAD_SUFFIX.sub("", raw).strip()
            if len(name) > 2:
                names.add(name)
                try:
                    points[name] = (
                        float(cells[idx["INTPTLAT"]]),
                        float(cells[idx["INTPTLONG"]]),
                    )
                except (ValueError, KeyError):
                    pass
        print(f"  gazetteer {year}: {len(names)} places")
        break
    return names, points


def corpus_names() -> set[str]:
    """Waterways and capitalised place lists harvested from real alert text."""
    waterway = dict(PATTERNS)["waterway"]
    out: set[str] = set()
    for f in ingest.load_cached():
        p = f.get("properties", {})
        blob = " ".join(
            str(p.get(k) or "") for k in ("description", "instruction", "areaDesc", "headline")
        )
        for m in waterway.finditer(blob):
            out.add(m.group(0).strip())
        # "Some locations that will experience flooding include... A, B and C."
        for m in re.finditer(r"include\.{0,3}\s*(.+?)(?:\.\s|\n\n|$)", blob, re.S):
            for cand in re.split(r",|\band\b", m.group(1)):
                cand = cand.strip().strip(".")
                if (
                    2 < len(cand) < 40
                    and cand[0].isupper()
                    and cand not in STOPWORDS
                    and not re.search(r"\d", cand)
                    and "\n" not in cand
                ):
                    out.add(cand)
    return out


def main() -> int:
    print("[1/3] NWS zones for VA")
    zones = nws_zones()
    print(f"      {len(zones)} names")

    print("[2/3] Census places (state 51)")
    places, points = census_places()
    print(f"      {len(places)} names, {len(points)} with centroids")

    print("[3/3] names harvested from the cached corpus")
    corpus = corpus_names()
    print(f"      {len(corpus)} names")

    names = {n for n in (zones | places | corpus) if n and n not in STOPWORDS}
    # Single lowercase tokens are false-positive machines; require a capital.
    names = {n for n in names if n[0].isupper()}

    payload = {
        "version": 1,
        "state": "VA",
        "sources": {
            "nws_zones": "api.weather.gov/zones?area=VA (keyless)",
            "census_places": "www2.census.gov Gazetteer place file, state 51 (keyless)",
            "corpus_harvested": "waterway + place-list spans from data/cached_alerts",
        },
        "counts": {"zones": len(zones), "census": len(places), "corpus": len(corpus), "total": len(names)},
        "names": sorted(names),
    }
    config.GAZETTEER_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nwrote {len(names)} names to {config.GAZETTEER_PATH}")

    if points:
        centroids = config.DATA_DIR / "va_place_points.json"
        centroids.write_text(
            json.dumps(
                {
                    "note": "Census Gazetteer place centroids, state 51. Offline geocoder "
                            "fallback only - a town centroid is not a street address.",
                    "points": {k: list(v) for k, v in sorted(points.items())},
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"wrote {len(points)} place centroids to {centroids}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
