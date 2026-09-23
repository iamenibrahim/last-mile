"""Day-1 job for the Disaster Assistance Navigator: cache everything to disk.

    python scripts/fetch_fema.py

  1. OpenFEMA disaster declarations for Virginia (keyless)
  2. Helene (DR-4831) registration counts by county - the impact figure
  3. IPAWS archived alerts from the Helene window - real warnings the NWS API
     no longer serves, which the alert pipeline can replay
  4. Authoritative source documents that answer scripted requests:
     eCFR 44 CFR Part 206 (the IHP regulation itself), SBA, SAMHSA

fema.gov and disasterassistance.gov return 403 to scripted clients. This script
does not try to get around that. See data/sources/README.md for how FEMA pages
enter the corpus instead.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from grounded import config, fema, sources  # noqa: E402

UA = {"User-Agent": config.NWS_USER_AGENT}

HTML_SOURCES = [
    ("sba-disaster", "Disaster assistance", "U.S. Small Business Administration",
     "https://www.sba.gov/funding-programs/disaster-assistance"),
    # The physical-damage-loans URL returned the same landing text as the page
    # above, so it is not listed: a document filed under a URL whose content it
    # does not actually hold would be false provenance.
    ("samhsa-ddh", "Disaster Distress Helpline", "Substance Abuse and Mental Health Services Administration",
     "https://www.samhsa.gov/find-help/disaster-distress-helpline"),
    ("samhsa-988", "988 Suicide & Crisis Lifeline", "Substance Abuse and Mental Health Services Administration",
     "https://www.samhsa.gov/find-help/988"),
]

# 44 CFR Part 206 Subpart D - Federal Assistance to Individuals and Households.
ECFR_SECTIONS = {
    "206.110": "Federal assistance to individuals and households",
    "206.112": "Registration period",
    "206.113": "Eligibility factors",
    "206.115": "Appeals",
    "206.117": "Housing assistance",
    "206.119": "Financial assistance to address other needs",
}


def html_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form", "noscript", "svg"]):
        tag.decompose()
    root = soup.find("main") or soup.find(attrs={"role": "main"}) or soup.body or soup
    blocks = []
    for el in root.find_all(["h1", "h2", "h3", "h4", "p", "li", "td", "th", "dt", "dd"]):
        t = el.get_text(" ", strip=True)
        if t and len(t) > 2:
            blocks.append(t)
    # De-duplicate nested repeats (an <li> containing a <p>) while keeping order.
    seen, out = set(), []
    for b in blocks:
        if b not in seen:
            seen.add(b)
            out.append(b)
    # get_text(" ") joins inline elements with a space, so a link followed by a
    # comma renders as "Text , call , or chat 988." Close that gap: a citation
    # should read the way the page reads.
    return re.sub(r"\s+([,.;:!?])", r"\1", "\n".join(out))


def fetch_ecfr() -> None:
    titles = httpx.get("https://www.ecfr.gov/api/versioner/v1/titles.json", headers=UA, timeout=40).json()
    as_of = next(t["up_to_date_as_of"] for t in titles["titles"] if t["number"] == 44)
    for sec, name in ECFR_SECTIONS.items():
        url = (f"https://www.ecfr.gov/api/versioner/v1/full/{as_of}/title-44.xml"
               f"?part=206&section={sec}")
        try:
            r = httpx.get(url, headers=UA, timeout=60, follow_redirects=True)
            r.raise_for_status()
        except Exception as exc:
            print(f"  eCFR {sec}: FAILED {exc}")
            continue
        text = BeautifulSoup(r.text, "html.parser").get_text("\n", strip=True)
        doc = sources.save(
            f"ecfr-44-{sec.replace('.', '-')}",
            title=f"44 CFR {sec} {name}",
            publisher="Electronic Code of Federal Regulations (eCFR)",
            url=f"https://www.ecfr.gov/current/title-44/section-{sec}",
            text=text,
            retrieval="scripted",
            transport=f"TLS to www.ecfr.gov versioner API, up to date as of {as_of}",
        )
        print(f"  eCFR {sec}: {len(doc.text):>6} chars  {doc.sha256[:12]}")


def fetch_html() -> None:
    for doc_id, title, publisher, url in HTML_SOURCES:
        try:
            r = httpx.get(url, headers=UA, timeout=45, follow_redirects=True)
            r.raise_for_status()
        except Exception as exc:
            print(f"  {doc_id}: FAILED {exc}")
            continue
        doc = sources.save(doc_id, title=title, publisher=publisher, url=url,
                           text=html_text(r.text), retrieval="scripted",
                           transport=f"TLS to {httpx.URL(url).host}")
        print(f"  {doc_id}: {len(doc.text):>6} chars  {doc.sha256[:12]}")


def main() -> int:
    print("[1/4] OpenFEMA declarations, Virginia, since 2015")
    snap = fema.fetch_declarations("VA", since="2015-01-01")
    dr = sorted({r["disasterNumber"] for r in snap["rows"]})
    print(f"      {snap['row_count']} designated-area rows across {len(dr)} declarations")

    print("[2/4] Helene (DR-4831) registrations")
    h = fema.fetch_housing(4831)
    s = fema.registrations_summary(4831)
    print(f"      {h['row_count']} rows, {s['valid_registrations']:,} valid registrations "
          f"({s['owner']:,} owner, {s['renter']:,} renter) in {s['counties']} areas")

    print("[3/4] IPAWS archive, Helene window, Smyth County")
    ip = fema.fetch_ipaws("2024-09-25T00:00:00.000Z", "2024-09-29T23:59:59.000Z", "Smyth")
    print(f"      {ip['row_count']} archived alerts")

    print("[4/4] authoritative source documents")
    fetch_ecfr()
    fetch_html()
    print(f"\ncorpus now holds {len(sources.corpus(reload=True))} documents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
