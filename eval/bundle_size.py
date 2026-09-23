from __future__ import annotations

import json
from pathlib import Path

from api.protocol import build_action_packet


ROOT = Path(__file__).resolve().parents[1]


def measure() -> dict:
    shell_files = [
        ROOT / "web" / "index.html",
        ROOT / "web" / "styles.css",
        ROOT / "web" / "app.js",
        ROOT / "web" / "sw.js",
        ROOT / "web" / "icon.svg",
        ROOT / "web" / "manifest.webmanifest",
    ]
    packet = build_action_packet(
        {
            "location": "24370",
            "jurisdiction": "Smyth County",
            "needs": ["home_repair", "housing", "documents"],
            "circumstances": ["displaced", "no_id"],
            "context_reviewed": True,
        }
    )["packet"]
    offline_payload = json.dumps(packet["channels"]["offline"], ensure_ascii=False).encode("utf-8")
    return {
        "cached_shell_bytes_uncompressed": sum(path.stat().st_size for path in shell_files),
        "offline_packet_bytes_uncompressed": len(offline_payload),
        "measurement_note": "Repository byte count before HTTP compression; not a network benchmark.",
    }

