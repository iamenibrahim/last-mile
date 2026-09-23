"""OpenFEMA: disaster declarations, registrations, and the IPAWS archive.

Everything here is keyless (https://www.fema.gov/about/openfema/api) and every
payload is cached to data/fema/ with the same canonicalise-and-hash provenance
the alert pipeline uses, so a navigator answer can be traced to the exact rows
it was built from.

The one rule this module exists to enforce: whether FEMA individual assistance
is available in a county is read from the declaration data, never inferred by
a model. The OpenFEMA data dictionary is explicit about how:

    "To determine which FEMA events have been authorized to receive Individual
     Assistance, use both ihProgramDeclared and iaProgramDeclared."
                          - DisasterDeclarationsSummaries v2, ihProgramDeclared

so `individual_assistance` below is `ih OR ia`, and the quote is the reason.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass, asdict
from typing import Iterable

import httpx

from . import config, ingest

OPENFEMA = "https://www.fema.gov/api/open"
FEMA_DIR = config.DATA_DIR / "fema"
TIMEOUT = httpx.Timeout(60.0, connect=10.0)

IA_RULE_SOURCE = (
    "OpenFEMA data dictionary, DisasterDeclarationsSummaries v2, field "
    "ihProgramDeclared: 'To determine which FEMA events have been authorized to "
    "receive Individual Assistance, use both ihProgramDeclared and iaProgramDeclared.'"
)

DECLARATION_TYPES = {
    "DR": "Major Disaster Declaration",
    "EM": "Emergency Declaration",
    "FM": "Fire Management Assistance Declaration",
}


def _get(path: str, params: dict | None = None) -> dict:
    r = httpx.get(
        f"{OPENFEMA}{path}",
        params=params,
        headers={"User-Agent": config.NWS_USER_AGENT},
        timeout=TIMEOUT,
        follow_redirects=True,
    )
    r.raise_for_status()
    return r.json()


def _paged(path: str, entity: str, filt: str, top: int = 1000, limit: int = 20000,
           orderby: str | None = None, select: str | None = None) -> list[dict]:
    """OpenFEMA caps $top at 1000 (10000 on some sets); page with $skip."""
    out: list[dict] = []
    skip = 0
    while skip < limit:
        params = {"$filter": filt, "$top": str(top), "$skip": str(skip)}
        if orderby:
            params["$orderby"] = orderby
        if select:
            params["$select"] = select
        rows = _get(path, params).get(entity, [])
        out.extend(rows)
        if len(rows) < top:
            break
        skip += top
    return out


def _snapshot(name: str, rows: list[dict], query: dict) -> dict:
    """Wrap rows in a provenance envelope and write them to data/fema/."""
    FEMA_DIR.mkdir(parents=True, exist_ok=True)
    envelope = {
        "dataset": name,
        "query": query,
        "fetched_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "transport": "TLS to www.fema.gov/api/open (OpenFEMA, keyless)",
        "row_count": len(rows),
        "rows": rows,
    }
    envelope["sha256"] = ingest.sha256_of({"rows": rows})
    envelope["canonicalization"] = "sha256 over json sorted-keys of {'rows': rows}"
    (FEMA_DIR / f"{name}.json").write_text(
        json.dumps(envelope, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    return envelope


def load_snapshot(name: str) -> dict | None:
    path = FEMA_DIR / f"{name}.json"
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def verify_snapshot(envelope: dict) -> bool:
    return envelope.get("sha256") == ingest.sha256_of({"rows": envelope.get("rows", [])})


# ---------------------------------------------------------------------------
# Fetchers (run by scripts/fetch_fema.py; the app reads snapshots from disk)
# ---------------------------------------------------------------------------


def fetch_declarations(state: str = "VA", since: str = "2015-01-01") -> dict:
    filt = f"state eq '{state}' and declarationDate ge '{since}T00:00:00.000Z'"
    rows = _paged("/v2/DisasterDeclarationsSummaries", "DisasterDeclarationsSummaries",
                  filt, orderby="declarationDate desc")
    return _snapshot(f"declarations_{state.lower()}", rows, {"filter": filt})


def fetch_housing(disaster_number: int) -> dict:
    filt = f"disasterNumber eq {disaster_number}"
    owners = _paged("/v2/HousingAssistanceOwners", "HousingAssistanceOwners", filt)
    renters = _paged("/v2/HousingAssistanceRenters", "HousingAssistanceRenters", filt)
    rows = [{**r, "_tenure": "owner"} for r in owners] + [{**r, "_tenure": "renter"} for r in renters]
    return _snapshot(f"housing_dr{disaster_number}", rows, {"filter": filt})


def fetch_ipaws(start: str, end: str, contains: str) -> dict:
    """IPAWS archived alerts. Public, keyless - live IPAWS needs a COG
    agreement, but FEMA publishes the archive on OpenFEMA."""
    filt = (f"sent ge '{start}' and sent le '{end}' and "
            f"contains(originalMessage,'{contains}')")
    rows = _paged("/v1/IpawsArchivedAlerts", "IpawsArchivedAlerts", filt, top=200, limit=2000)
    slug = re.sub(r"[^a-z0-9]+", "_", contains.lower()).strip("_")
    return _snapshot(f"ipaws_{slug}_{start[:10]}", rows, {"filter": filt})


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------


@dataclass
class DeclarationStatus:
    disaster_number: int
    declaration_string: str
    declaration_type: str
    declaration_type_name: str
    title: str
    incident_type: str
    declaration_date: str
    incident_begin: str | None
    incident_end: str | None
    designated_area: str
    fips: str
    individual_assistance: bool
    public_assistance: bool
    hazard_mitigation: bool
    ih_declared: bool
    ia_declared: bool
    last_ia_filing_date: str | None
    ia_rule: str = IA_RULE_SOURCE

    def to_dict(self) -> dict:
        return asdict(self)


def _fips(row: dict) -> str:
    return f"{row.get('fipsStateCode', '')}{row.get('fipsCountyCode', '')}"


def _status(row: dict) -> DeclarationStatus:
    ih = bool(row.get("ihProgramDeclared"))
    ia = bool(row.get("iaProgramDeclared"))
    dtype = row.get("declarationType", "")
    return DeclarationStatus(
        disaster_number=int(row["disasterNumber"]),
        declaration_string=row.get("femaDeclarationString") or f"{dtype}-{row['disasterNumber']}",
        declaration_type=dtype,
        declaration_type_name=DECLARATION_TYPES.get(dtype, dtype),
        title=(row.get("declarationTitle") or "").title(),
        incident_type=row.get("incidentType") or "",
        declaration_date=row.get("declarationDate") or "",
        incident_begin=row.get("incidentBeginDate"),
        incident_end=row.get("incidentEndDate"),
        designated_area=row.get("designatedArea") or "",
        fips=_fips(row),
        individual_assistance=ih or ia,
        public_assistance=bool(row.get("paProgramDeclared")),
        hazard_mitigation=bool(row.get("hmProgramDeclared")),
        ih_declared=ih,
        ia_declared=ia,
        # Only meaningful when IA was approved (data dictionary, lastIAFilingDate).
        last_ia_filing_date=row.get("lastIAFilingDate") if (ih or ia) else None,
    )


def declarations_for_county(fips: str, rows: Iterable[dict] | None = None,
                            state: str = "VA") -> list[DeclarationStatus]:
    """Every declaration whose designated area is this county, newest first.

    Statewide designations ("Statewide", fipsCountyCode 000) also apply to the
    county and are included.
    """
    if rows is None:
        snap = load_snapshot(f"declarations_{state.lower()}")
        rows = snap["rows"] if snap else []
    state_fips = fips[:2]
    out = [
        _status(r) for r in rows
        if _fips(r) == fips or (r.get("fipsStateCode") == state_fips and r.get("fipsCountyCode") == "000")
    ]
    # One row per (disaster, area); keep the newest designation.
    seen: dict[int, DeclarationStatus] = {}
    for s in sorted(out, key=lambda s: s.declaration_date):
        seen[s.disaster_number] = s
    return sorted(seen.values(), key=lambda s: s.declaration_date, reverse=True)


# 44 CFR 206.112(d): "After the standard or extended registration period ends,
# FEMA will accept late registrations for an additional 60 days." The number is
# the regulation's, and the navigator shows that sentence next to any figure
# computed from it.
LATE_REGISTRATION_DAYS = 60


def registration_window(status: DeclarationStatus, now: dt.datetime | None = None) -> dict:
    """Where a household stands against the deadline, from lastIAFilingDate.

    Three live states, not two - "open", then "late" (the 60-day late window
    in 206.112(d), open to registrants who explain the delay), then "closed".
    Collapsing late into closed would tell people it is over while the
    regulation says it is not.

    Deadlines are sometimes extended after the fact, and the snapshot is only
    as current as its fetch. That caveat is part of the return value because it
    has to be part of every sentence built from it.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    caveat = ("Deadline as recorded in OpenFEMA at the time of the last data fetch. "
              "FEMA can extend deadlines - confirm with the FEMA Helpline before relying on it.")
    blank = {"days_left": None, "deadline": None, "late_until": None, "late_days_left": None}
    if not status.individual_assistance:
        return {"state": "not_applicable", **blank, "caveat": None}
    if not status.last_ia_filing_date:
        return {"state": "unknown", **blank, "caveat": caveat}
    deadline = dt.datetime.fromisoformat(status.last_ia_filing_date.replace("Z", "+00:00"))
    # The date is the last day to file, so it is open through the end of it.
    end = deadline + dt.timedelta(days=1)
    late_end = end + dt.timedelta(days=LATE_REGISTRATION_DAYS)
    days = (end - now).total_seconds() / 86400
    late_days = (late_end - now).total_seconds() / 86400
    if days > 0:
        state = "open"
    elif late_days > 0:
        state = "late"
    else:
        state = "closed"
    return {
        "state": state,
        "days_left": int(days) if days > 0 else 0,
        "deadline": status.last_ia_filing_date[:10],
        "late_until": (late_end - dt.timedelta(days=1)).strftime("%Y-%m-%d"),
        "late_days_left": int(late_days) if state == "late" else 0,
        "caveat": caveat,
    }


def registrations_summary(disaster_number: int) -> dict | None:
    """Valid registrations by county, for the impact figure."""
    snap = load_snapshot(f"housing_dr{disaster_number}")
    if not snap:
        return None
    by_county: dict[str, dict] = {}
    for r in snap["rows"]:
        c = by_county.setdefault(r["county"], {"owner": 0, "renter": 0})
        c[r["_tenure"]] += int(r.get("validRegistrations") or 0)
    total_owner = sum(c["owner"] for c in by_county.values())
    total_renter = sum(c["renter"] for c in by_county.values())
    return {
        "disaster_number": disaster_number,
        "valid_registrations": total_owner + total_renter,
        "owner": total_owner,
        "renter": total_renter,
        "counties": len(by_county),
        "by_county": by_county,
        "source": f"OpenFEMA HousingAssistanceOwners + HousingAssistanceRenters, disasterNumber {disaster_number}",
        "sha256": snap["sha256"],
        "fetched_at": snap["fetched_at"],
    }


# ---------------------------------------------------------------------------
# IPAWS archive -> the alert pipeline's feature shape
# ---------------------------------------------------------------------------

CAP_NS = {"cap": "urn:oasis:names:tc:emergency:cap:1.2"}


def ipaws_to_feature(row: dict) -> dict | None:
    """Convert an archived IPAWS CAP message into the NWS-API feature shape the
    alert transformer already consumes, keeping the original XML's hash.

    Lets the existing alert pipeline replay real Helene-era warnings - the data
    the NWS API's one-week window no longer serves.
    """
    import xml.etree.ElementTree as ET

    raw = row.get("originalMessage") or ""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return None
    info = root.find("cap:info", CAP_NS)
    if info is None:
        return None

    def t(node, tag):
        el = node.find(f"cap:{tag}", CAP_NS)
        return el.text.strip() if el is not None and el.text else None

    area = info.find("cap:area", CAP_NS)
    polygon = area.find("cap:polygon", CAP_NS) if area is not None else None
    geometry = None
    if polygon is not None and polygon.text:
        coords = []
        for pair in polygon.text.split():
            lat, lon = pair.split(",")
            coords.append([float(lon), float(lat)])
        geometry = {"type": "Polygon", "coordinates": [coords]}

    geocode = {}
    if area is not None:
        for g in area.findall("cap:geocode", CAP_NS):
            name, value = t(g, "valueName"), t(g, "value")
            if name and value:
                geocode.setdefault(name, []).extend(value.split())

    identifier = t(root, "identifier")
    feature = {
        "id": identifier,
        "type": "Feature",
        "geometry": geometry,
        "properties": {
            "id": identifier,
            "@id": f"{OPENFEMA}/v1/IpawsArchivedAlerts?$filter=identifier eq '{identifier}'",
            "sent": t(root, "sent"),
            "status": t(root, "status"),
            "messageType": t(root, "msgType"),
            "event": t(info, "event"),
            "severity": t(info, "severity"),
            "certainty": t(info, "certainty"),
            "urgency": t(info, "urgency"),
            "headline": t(info, "headline"),
            "description": t(info, "description"),
            "instruction": t(info, "instruction"),
            "onset": t(info, "onset"),
            "effective": t(info, "effective"),
            "expires": t(info, "expires"),
            "senderName": t(info, "senderName"),
            "areaDesc": t(area, "areaDesc") if area is not None else None,
            "geocode": geocode,
            "affectedZones": [],
        },
    }
    feature["_provenance"] = {
        "url": feature["properties"]["@id"],
        "cap_id": identifier,
        "sha256": ingest.sha256_of(feature),
        "original_xml_sha256": __import__("hashlib").sha256(raw.encode("utf-8")).hexdigest(),
        "sender": feature["properties"]["senderName"],
        "sent": feature["properties"]["sent"],
        "fetched_at": row.get("_fetched_at"),
        "transport": "TLS to www.fema.gov/api/open (OpenFEMA IPAWS archive)",
        "trust_anchor": ingest.TRUST_ANCHOR_NOTE,
        "canonicalization": "json sorted-keys, no whitespace, utf-8, _provenance excluded",
    }
    return feature
