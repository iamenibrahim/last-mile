from __future__ import annotations

import hashlib
import hmac
import json
from copy import deepcopy
from datetime import datetime, timezone

from . import signing
from .ingest import canonicalize, payload_hash


def _unsigned(manifest: dict) -> dict:
    value = deepcopy(manifest)
    value.pop("signature", None)
    return value


def _message(manifest: dict) -> bytes:
    return canonicalize(_unsigned(manifest)).encode("utf-8")


def build_manifest(alert: dict, chain: list[dict], segments: list[dict], rendered_text: str) -> dict:
    properties = alert.get("properties", {})
    source_url = properties.get("@id") or alert.get("id") or "unknown"
    is_demo = bool(properties.get("demo_notice")) or str(properties.get("id", "")).startswith("urn:demo:")
    manifest = {
        "schema": "https://last-mile.example/schemas/manifest/v1",
        "source": {
            "url": source_url,
            "cap_id": properties.get("id") or alert.get("id"),
            "sha256": payload_hash(alert),
            "sender": properties.get("senderName") or properties.get("sender"),
            "sent": properties.get("sent"),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "transport": "local demo fixture" if is_demo else "TLS to api.weather.gov",
        },
        "transform_chain": chain,
        "segments": segments,
        "rendered_sha256": hashlib.sha256(rendered_text.encode("utf-8")).hexdigest(),
        "trust_boundary": (
            "This is a synthetic NWS-schema demo fixture, not an active alert and not an NWS-signed artifact. "
            "The manifest signature covers this local fixture and its transformation."
            if is_demo
            else "NWS CAP alerts are not individually end-to-end signed. This signature attests to "
            "the payload fetched over TLS and this transformation—not an NWS digital signature."
        ),
    }
    # key_id and algorithm are inside the signed body, so they cannot be swapped.
    signer = signing.describe()
    manifest["signing"] = {"key_id": signer["key_id"], "algorithm": signer["algorithm"]}
    manifest["signature"] = signing.sign(_message(manifest))["signature"]
    return manifest


def validate_manifest(manifest: dict, rendered_text: str | None = None) -> dict:
    signature_valid = signing.verify(_message(manifest), manifest.get("signature", ""))
    content_valid = True
    if rendered_text is not None:
        content_valid = hmac.compare_digest(
            manifest.get("rendered_sha256", ""),
            hashlib.sha256(rendered_text.encode("utf-8")).hexdigest(),
        )
    return {
        "valid": signature_valid and content_valid,
        "signature_valid": signature_valid,
        "content_valid": content_valid,
        "trust_boundary": manifest.get("trust_boundary"),
    }
