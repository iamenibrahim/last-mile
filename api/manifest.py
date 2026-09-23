from __future__ import annotations

import hashlib
import hmac
import json
from copy import deepcopy
from datetime import datetime, timezone

from .config import settings
from .ingest import canonicalize, payload_hash


def _unsigned(manifest: dict) -> dict:
    value = deepcopy(manifest)
    value.pop("signature", None)
    return value


def sign_manifest(manifest: dict) -> str:
    message = canonicalize(_unsigned(manifest)).encode("utf-8")
    return hmac.new(settings.manifest_signing_key.encode("utf-8"), message, hashlib.sha256).hexdigest()


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
        "signature_method": "HMAC-SHA256 local demo; Azure Key Vault key in deployment",
    }
    manifest["signature"] = sign_manifest(manifest)
    return manifest


def validate_manifest(manifest: dict, rendered_text: str | None = None) -> dict:
    supplied = manifest.get("signature", "")
    expected = sign_manifest(manifest)
    signature_valid = hmac.compare_digest(supplied, expected)
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
