"""Admit browser-captured FEMA pages into the source corpus - or refuse them.

fema.gov returns HTTP 403 to scripted clients, and this project does not try to
get around that. FEMA pages were instead read in an ordinary browser view, and
each page's visible text was hashed *inside the browser* (SHA-256 of the text
normalised by sources.NORMALISE_JS) at the moment of capture.

The text was then written to data/sources/browser/*.txt by hand-off, and that
hand-off is exactly where a transcription error could slip in unnoticed. So this
script re-normalises every file with the Python twin of the same function and
compares hashes. A file that does not reproduce the browser's hash is rejected,
not "fixed": a corpus that cites FEMA must contain what FEMA published.

    python scripts/ingest_browser_sources.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from grounded import sources  # noqa: E402

BROWSER_DIR = sources.SOURCES_DIR / "browser"


def parse(path: Path) -> tuple[dict, str]:
    raw = path.read_text(encoding="utf-8")
    header, _, body = raw.partition("\n---\n")
    meta = {}
    for line in header.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, body


def main() -> int:
    ok = bad = 0
    for path in sorted(BROWSER_DIR.glob("*.txt")):
        meta, body = parse(path)
        normalised = sources.normalise(body)
        actual = sources.text_sha256(normalised)
        expected = meta.get("browser_sha256", "")
        if actual != expected:
            bad += 1
            print(f"  REJECT {meta.get('id', path.stem):22s} hash {actual[:12]} != browser {expected[:12]} "
                  f"({len(normalised)} chars)")
            continue
        doc = sources.save(
            meta["id"],
            title=meta["title"],
            publisher=meta["publisher"],
            url=meta["url"],
            text=body,
            retrieval="browser",
            transport="ordinary browser page view of " + meta["url"] + "; fema.gov returns 403 to scripted clients",
            note=(f"lang={meta.get('lang', 'en')}; page 'last updated' {meta.get('last_updated')}; "
                  f"text hashed in-browser at capture and re-verified on ingest"),
        )
        ok += 1
        print(f"  admit  {doc.id:22s} {len(doc.text):>5} chars  sha {doc.sha256[:12]}  (matches browser)")
    print(f"\n{ok} admitted, {bad} rejected")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
