"""Day-1 job: pull real alerts to disk so the demo never touches live data.

The NWS public archive window is short (empirically about the last week), so
this must be run early and often. Nothing here fabricates an alert: every file
written is a real NWS CAP product with its real areaDesc, sender and timestamps.

    python scripts/fetch_corpus.py            # VA, last 7 days + active
    python scripts/fetch_corpus.py --days 7 --national
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from grounded import config, ingest  # noqa: E402

# Events whose instruction field actually carries protective action, used to
# pick demo candidates. Not a filter on the eval corpus.
ACTIONABLE = {
    "Flash Flood Warning",
    "Flood Warning",
    "Flood Advisory",
    "Tornado Warning",
    "Severe Thunderstorm Warning",
    "Hurricane Warning",
    "Tropical Storm Warning",
    "Storm Surge Warning",
    "Coastal Flood Warning",
    "High Wind Warning",
    "Winter Storm Warning",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", default="VA")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--national", action="store_true",
                    help="also cache active actionable alerts nationwide, for richer instruction text")
    args = ap.parse_args()

    out = config.CACHED_ALERTS_DIR
    out.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)
    start = (now - dt.timedelta(days=args.days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    everything: list[dict] = []

    print(f"[1/3] {args.area} archive since {start}")
    try:
        window = ingest.fetch_window(area=args.area, start=start)
        print(f"      {len(window)} alerts")
        everything += window
    except Exception as exc:
        print(f"      FAILED: {exc}")

    print(f"[2/3] {args.area} active now")
    try:
        active = ingest.fetch_active(area=args.area)
        print(f"      {len(active)} alerts")
        everything += active
    except Exception as exc:
        print(f"      FAILED: {exc}")

    if args.national:
        print("[3/3] national active, actionable events only")
        try:
            nat = ingest.fetch_active(area="")
            picked = [
                f for f in nat
                if f["properties"].get("event") in ACTIONABLE
                and f.get("geometry")
                and (f["properties"].get("instruction") or "").strip()
            ]
            print(f"      {len(nat)} active nationwide, {len(picked)} actionable with geometry+instruction")
            everything += picked[:40]
        except Exception as exc:
            print(f"      FAILED: {exc}")
    else:
        print("[3/3] skipped national pull")

    # De-duplicate by CAP id, newest wins.
    by_id: dict[str, dict] = {}
    for f in everything:
        by_id[ingest.alert_id(f)] = f

    n = ingest.save_cached(by_id.values())
    print(f"\nwrote {n} alerts to {out}")

    events = Counter(f["properties"].get("event") for f in by_id.values())
    with_instr = sum(1 for f in by_id.values() if (f["properties"].get("instruction") or "").strip())
    with_geom = sum(1 for f in by_id.values() if f.get("geometry"))
    print(f"  with instruction: {with_instr}/{n}")
    print(f"  with geometry:    {with_geom}/{n}")
    print("  events:")
    for ev, c in events.most_common():
        print(f"    {c:3d}  {ev}")

    manifest = {
        "fetched_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "area": args.area,
        "window_days": args.days,
        "count": n,
        "with_instruction": with_instr,
        "with_geometry": with_geom,
        "events": dict(events),
        "note": "Real NWS CAP products. No alert in this directory is synthetic.",
    }
    (out / "_corpus_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
