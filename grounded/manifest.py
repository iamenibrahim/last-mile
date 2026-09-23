"""Provenance manifest: build, sign, validate.

Brief section 3.2. Every rendered output carries a manifest, and a `verify`
endpoint takes one back and says whether it holds up.

WHAT A VALID MANIFEST ACTUALLY PROVES - the honesty boundary, INVARIANT:

    It proves that THIS system fetched THAT byte sequence from api.weather.gov
    over TLS at THAT time, and produced THIS rendering from it, with THESE
    segments verified and THOSE abstained.

    It does NOT prove the National Weather Service signed anything. NWS CAP
    products served over api.weather.gov are not individually signed in a way
    this system can verify end to end. The trust anchor is TLS to the NWS
    origin plus our own signature over what we fetched. A manifest that
    validates tells you the transformation is faithful to a fetch we attest to.
    It cannot, by itself, tell you the fetch was genuine.

    C2PA Content Credentials are the real path to closing that gap. Not built.

That limitation is written into every manifest as `trust_anchor` and returned
by every validation as `limitations`, so it travels with the artifact instead
of living only on a slide - which is the difference between disclosing a limit
and being caught by it.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Any

from . import ingest
from .providers.base import get_registry

MANIFEST_VERSION = "1.0"

TRUST_ANCHOR = (
    "TLS to api.weather.gov, plus this system's own signature over the bytes it "
    "fetched. This is NOT a verified NWS digital signature: NWS CAP products "
    "served over this API are not individually signed in a way this system can "
    "verify end to end. A valid manifest proves faithful transformation of a "
    "fetch we attest to, not the authenticity of the fetch itself."
)

LIMITATIONS = [
    TRUST_ANCHOR,
    "The local development signer is HMAC-SHA256, which is symmetric: anyone "
    "able to verify is also able to forge. Asymmetric signing via Azure Key "
    "Vault is implemented and is the deployment path.",
    "C2PA Content Credentials are cited as future work and are not implemented.",
]


def _js_numbers(obj: Any) -> Any:
    """Normalise numbers the way ECMAScript serialises them.

    This is not fussiness, it is the difference between a verify button that
    works and one that always fails. A manifest is signed in Python, shipped to
    a browser, and posted back for verification. Python writes `7.0`;
    JavaScript's JSON.stringify writes `7` for the same value, because
    ECMAScript has one number type and drops a trailing `.0`. The bytes then
    differ, the HMAC differs, and every honest manifest reads as tampered.

    RFC 8785 (JSON Canonicalization Scheme) settles this by defining
    canonical number output as ECMAScript's `Number::toString`. Collapsing
    integral floats to integers is the part of that rule this data actually
    exercises: the values at risk are `target_grade: 7.0` and rounded
    distances. Non-integral floats already agree, because Python's repr and
    ECMAScript both emit the shortest round-tripping form.
    """
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, float):
        if obj != obj or obj in (float("inf"), float("-inf")):
            raise ValueError("non-finite numbers cannot be canonicalised")
        return int(obj) if obj.is_integer() else obj
    if isinstance(obj, dict):
        return {k: _js_numbers(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_js_numbers(v) for v in obj]
    return obj


def canonical_bytes(obj: Any) -> bytes:
    """Sorted keys, no whitespace, UTF-8, ECMAScript number formatting.

    Stable across a Python -> JSON -> JavaScript -> JSON -> Python round trip,
    which is exactly the path a manifest takes between signing and verifying.
    """
    return json.dumps(
        _js_numbers(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def render_digest(render: dict) -> str:
    """Hash binding the manifest to the exact text that was shown.

    Covers segment id, status and output text - the three things a reader
    could be misled about. Deliberately excludes timing and provider notes so
    that re-rendering the same content does not invalidate the binding.
    """
    payload = [
        {"id": s["id"], "status": s["status"], "output_text": s.get("output_text", "")}
        for s in render.get("segments", [])
    ]
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def build(render: dict, feature: dict) -> dict:
    """Assemble the unsigned manifest for one rendering."""
    prov = feature.get("_provenance") or ingest.annotate(feature, "unknown")["_provenance"]
    props = feature.get("properties", {})

    return {
        "manifest_version": MANIFEST_VERSION,
        "source": {
            "url": prov.get("url"),
            "cap_id": prov.get("cap_id") or props.get("id"),
            "sha256": prov.get("sha256"),
            "sender": prov.get("sender") or props.get("senderName"),
            "sent": prov.get("sent") or props.get("sent"),
            "fetched_at": prov.get("fetched_at"),
            "transport": prov.get("transport", "TLS to api.weather.gov"),
            "canonicalization": prov.get("canonicalization"),
            "trust_anchor": TRUST_ANCHOR,
        },
        "render": {
            "render_id": render.get("render_id"),
            "language": render.get("language"),
            "target_grade": render.get("target_grade"),
            "created_at": render.get("created_at"),
            "digest_sha256": render_digest(render),
            "digest_covers": "segment id, status and output_text, canonical JSON",
        },
        "transform_chain": render.get("transform_chain", []),
        "segments": [
            {
                "id": s["id"],
                "status": s["status"],
                **({"reason": s["reason"]} if s.get("reason") else {}),
            }
            for s in render.get("segments", [])
        ],
        "abstained_count": render.get("abstained_count", 0),
        "segment_count": render.get("segment_count", 0),
        "providers": render.get("providers", {}),
        "limitations": LIMITATIONS,
    }


def sign(manifest: dict) -> dict:
    """Attach a signature over the canonical bytes of everything else."""
    signer = get_registry().signer
    unsigned = {k: v for k, v in manifest.items() if k != "signature"}
    payload = canonical_bytes(unsigned)
    manifest["signature"] = {
        "value": signer.sign(payload),
        "algorithm": getattr(signer, "algorithm", "unknown"),
        "key_id": getattr(signer, "key_id", "unknown"),
        "signer": getattr(signer, "name", "unknown"),
        "signed_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "covers": "canonical JSON of this manifest with the signature field removed",
    }
    return manifest


def build_signed(render: dict, feature: dict) -> dict:
    return sign(build(render, feature))


# ---------------------------------------------------------------------------
# Navigator manifests
# ---------------------------------------------------------------------------

NAVIGATOR_LIMITATIONS = [
    "FEMA pages were captured from an ordinary browser view, because fema.gov "
    "returns HTTP 403 to scripted clients. Their text was hashed in the browser at "
    "capture and re-verified on ingest; the hash proves the corpus matches that "
    "capture, not that FEMA has not since changed the page.",
    "Eligibility indicators come from OpenFEMA declaration flags. FEMA decides "
    "eligibility; this page never does.",
    "Deadlines are as recorded in OpenFEMA at the last fetch. FEMA can extend them.",
    LIMITATIONS[1],
]


def build_navigator(render: dict) -> dict:
    """Manifest for a navigator page: every cited document, the declaration
    data, what was retained about the person, and each segment's citation."""
    segments = []
    for s in render.get("segments", []):
        entry = {"id": s["id"], "status": s["status"], "role": s["role"]}
        if s.get("reason"):
            entry["reason"] = s["reason"]
        cite = (s.get("meta") or {}).get("citation")
        if cite:
            entry["citation"] = {"doc_id": cite["doc_id"], "start": cite["start"], "end": cite["end"],
                                 "doc_sha256": cite["doc_sha256"]}
        segments.append(entry)
    decl = render.get("declarations") or {}
    primary = decl.get("primary") or {}
    return {
        "manifest_version": MANIFEST_VERSION,
        "kind": "navigator",
        "sources": [
            {k: d.get(k) for k in ("id", "url", "publisher", "retrieval", "sha256", "fetched_at")}
            for d in render.get("sources_used", [])
        ],
        "data": {
            **(decl.get("source") or {}),
            "county_fips": (render.get("county") or {}).get("fips"),
            "primary_declaration": primary.get("declaration_string"),
        },
        "render": {
            "render_id": render.get("render_id"),
            "language": render.get("language"),
            "created_at": render.get("created_at"),
            "as_of": render.get("as_of"),
            "digest_sha256": render_digest(render),
            "digest_covers": "segment id, status and output_text, canonical JSON",
        },
        "retained": {
            "county_fips": (render.get("county") or {}).get("fips"),
            "needs": render.get("needs", []),
            "escalation_level": (render.get("escalation") or {}).get("level"),
            "not_retained": "the location text you typed, and any free text",
        },
        "transform_chain": render.get("transform_chain", []),
        "segments": segments,
        "abstained_count": render.get("abstained_count", 0),
        "segment_count": render.get("segment_count", 0),
        "providers": render.get("providers", {}),
        "limitations": NAVIGATOR_LIMITATIONS,
    }


def build_navigator_signed(render: dict) -> dict:
    return sign(build_navigator(render))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@dataclass
class Check:
    name: str
    passed: bool
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ValidationReport:
    valid: bool
    checks: list[Check] = field(default_factory=list)
    source_text: dict | None = None
    limitations: list[str] = field(default_factory=lambda: list(LIMITATIONS))

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "checks": [c.to_dict() for c in self.checks],
            "source_text": self.source_text,
            "limitations": self.limitations,
            "what_this_proves": (
                "Faithful transformation of a fetch this system attests to. "
                "NOT the authenticity of the source fetch itself."
            ),
        }


def validate(manifest: dict, feature: dict | None = None,
             rendered_segments: list[dict] | None = None) -> ValidationReport:
    """Check a manifest. Every failure is reported; validation never throws."""
    report = ValidationReport(valid=True)

    def add(name: str, ok: bool, detail: str) -> None:
        report.checks.append(Check(name, ok, detail))
        if not ok:
            report.valid = False

    navigator = isinstance(manifest, dict) and manifest.get("kind") == "navigator"
    if not isinstance(manifest, dict) or ("source" not in manifest and not navigator):
        add("well_formed", False, "not a manifest: missing 'source'")
        return report
    add("well_formed", True, f"manifest_version {manifest.get('manifest_version')}"
        + (", navigator" if navigator else ""))
    if navigator:
        report.limitations = list(NAVIGATOR_LIMITATIONS)

    # --- signature ---------------------------------------------------------
    sig = manifest.get("signature")
    if not sig:
        add("signature_present", False, "no signature block")
    else:
        add("signature_present", True, f"{sig.get('algorithm')} via {sig.get('signer')}")
        signer = get_registry().signer
        if sig.get("key_id") != getattr(signer, "key_id", None):
            add(
                "signature_key",
                False,
                f"manifest was signed with key_id {sig.get('key_id')!r}, but this "
                f"instance holds {getattr(signer, 'key_id', None)!r}; cannot verify",
            )
        else:
            unsigned = {k: v for k, v in manifest.items() if k != "signature"}
            try:
                ok = signer.verify(canonical_bytes(unsigned), sig.get("value", ""))
            except Exception as exc:
                ok = False
                add("signature_valid", False, f"verification error: {type(exc).__name__}: {exc}")
            else:
                add(
                    "signature_valid",
                    ok,
                    "signature matches the manifest contents"
                    if ok
                    else "SIGNATURE DOES NOT MATCH - the manifest was altered after signing",
                )

    # --- navigator: every cited document, and every citation's exact words ---
    if navigator:
        from . import sources as src

        corpus = src.corpus()
        for d in manifest.get("sources", []):
            local = corpus.get(d.get("id"))
            if local is None:
                add(f"source:{d.get('id')}", True,
                    "not in this instance's corpus, so its hash was not recomputed")
            else:
                add(f"source:{d.get('id')}", local.sha256 == d.get("sha256"),
                    f"cached copy hash {local.sha256[:16]}"
                    + ("" if local.sha256 == d.get("sha256") else " DIFFERS from the manifest"))
        if rendered_segments is not None:
            by_id = {s.get("id"): s for s in rendered_segments}
            checked = bad = 0
            for entry in manifest.get("segments", []):
                cite = entry.get("citation")
                seg = by_id.get(entry["id"])
                if not cite or seg is None or cite["doc_id"] not in corpus:
                    continue
                checked += 1
                sliced = corpus[cite["doc_id"]].text[cite["start"]:cite["end"]]
                if sliced != seg.get("source_text"):
                    bad += 1
            add("citations_exact", bad == 0,
                f"{checked - bad}/{checked} citations slice to the exact quoted words in the cached source")
        # A navigator manifest has no single alert to hash; skip to the render
        # binding and the internal consistency checks below.
        feature = None
        manifest = {**manifest, "source": {"sha256": None}}

    # --- source hash -------------------------------------------------------
    recorded = manifest["source"].get("sha256")
    if navigator:
        pass
    elif feature is None:
        add("source_hash", True,
            f"recorded {recorded}; no local copy of the source supplied, so not recomputed")
    else:
        actual = ingest.sha256_of(feature)
        add(
            "source_hash",
            actual == recorded,
            f"recomputed {actual}"
            + ("" if actual == recorded else f" but manifest records {recorded} - SOURCE ALTERED"),
        )
        props = feature.get("properties", {})
        report.source_text = {
            "event": props.get("event"),
            "sender": props.get("senderName"),
            "areaDesc": props.get("areaDesc"),
            "sent": props.get("sent"),
            "headline": props.get("headline"),
            "description": props.get("description"),
            "instruction": props.get("instruction"),
        }

    # --- render binding ----------------------------------------------------
    if rendered_segments is not None:
        payload = [
            {"id": s.get("id"), "status": s.get("status"), "output_text": s.get("output_text", "")}
            for s in rendered_segments
        ]
        actual = hashlib.sha256(canonical_bytes(payload)).hexdigest()
        recorded_digest = (manifest.get("render") or {}).get("digest_sha256")
        add(
            "render_digest",
            actual == recorded_digest,
            "rendered text matches the manifest"
            if actual == recorded_digest
            else f"rendered text does NOT match: computed {actual}, manifest records {recorded_digest}",
        )

    # --- internal consistency ---------------------------------------------
    segments = manifest.get("segments", [])
    declared = manifest.get("segment_count")
    if declared is not None:
        add("segment_count", declared == len(segments),
            f"{len(segments)} segment entries, manifest declares {declared}")
    abstained = sum(1 for s in segments if s.get("status") == "verbatim_abstained")
    declared_abstained = manifest.get("abstained_count")
    if declared_abstained is not None:
        add("abstained_count", declared_abstained == abstained,
            f"{abstained} abstained segments, manifest declares {declared_abstained}")

    chain = manifest.get("transform_chain", [])
    add("transform_chain", bool(chain), f"{len(chain)} steps recorded")

    injected = [s for s in chain if s.get("step") == "corruption_injected"]
    if injected:
        add(
            "no_injected_corruption",
            False,
            "this render was produced with adversarial corruption injected "
            "(eval harness / refusal demo) and is not a production artifact",
        )

    return report
