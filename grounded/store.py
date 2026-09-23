"""Storage behind a thin interface so the SQLite -> Cosmos swap is one file.

Brief section 5. Nothing above this module knows which backend is live.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Protocol

from . import config

DB_PATH = config.DATA_DIR / "last_mile.sqlite3"


class Store(Protocol):
    def put_alert(self, alert_id: str, doc: dict) -> None: ...
    def get_alert(self, alert_id: str) -> dict | None: ...
    def list_alerts(self, limit: int = 200) -> list[dict]: ...
    def put_render(self, render_id: str, doc: dict) -> None: ...
    def get_render(self, render_id: str) -> dict | None: ...
    def put_audio(self, render_id: str, lang: str, blob: bytes, mime: str) -> None: ...
    def get_audio(self, render_id: str, lang: str) -> tuple[bytes, str] | None: ...


class SqliteStore:
    """Default backend. One file, no server, safe across FastAPI's threadpool."""

    name = "sqlite"

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or DB_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init()

    def _init(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS alerts (
                    id TEXT PRIMARY KEY,
                    sent TEXT,
                    event TEXT,
                    area_desc TEXT,
                    sha256 TEXT,
                    doc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS renders (
                    id TEXT PRIMARY KEY,
                    alert_id TEXT,
                    lang TEXT,
                    created_at TEXT,
                    doc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audio (
                    render_id TEXT,
                    lang TEXT,
                    mime TEXT,
                    blob BLOB,
                    PRIMARY KEY (render_id, lang)
                );
                CREATE INDEX IF NOT EXISTS idx_alerts_sent ON alerts(sent DESC);
                """
            )
            self._conn.commit()

    def put_alert(self, alert_id: str, doc: dict) -> None:
        props = doc.get("properties", {})
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO alerts (id, sent, event, area_desc, sha256, doc)"
                " VALUES (?,?,?,?,?,?)",
                (
                    alert_id,
                    props.get("sent"),
                    props.get("event"),
                    props.get("areaDesc"),
                    doc.get("_provenance", {}).get("sha256"),
                    json.dumps(doc, ensure_ascii=False),
                ),
            )
            self._conn.commit()

    def get_alert(self, alert_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT doc FROM alerts WHERE id = ?", (alert_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list_alerts(self, limit: int = 200) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT doc FROM alerts ORDER BY sent DESC LIMIT ?", (limit,)
            ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def put_render(self, render_id: str, doc: dict) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO renders (id, alert_id, lang, created_at, doc)"
                " VALUES (?,?,?,?,?)",
                (
                    render_id,
                    doc.get("alert_id"),
                    doc.get("language"),
                    doc.get("created_at"),
                    json.dumps(doc, ensure_ascii=False),
                ),
            )
            self._conn.commit()

    def get_render(self, render_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT doc FROM renders WHERE id = ?", (render_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def put_audio(self, render_id: str, lang: str, blob: bytes, mime: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO audio (render_id, lang, mime, blob) VALUES (?,?,?,?)",
                (render_id, lang, mime, blob),
            )
            self._conn.commit()

    def get_audio(self, render_id: str, lang: str) -> tuple[bytes, str] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT blob, mime FROM audio WHERE render_id = ? AND lang = ?", (render_id, lang)
            ).fetchone()
        return (row[0], row[1]) if row else None

    def close(self) -> None:
        with self._lock:
            self._conn.close()


class CosmosStore:  # pragma: no cover - deploy target, not exercised locally
    """Cosmos DB backend. Same interface, swapped by AZURE_COSMOS_URL."""

    name = "cosmos"

    def __init__(self) -> None:
        az = config.AZURE
        if not (az.cosmos_url and az.cosmos_key):
            raise RuntimeError("AZURE_COSMOS_URL / AZURE_COSMOS_KEY not set")
        from azure.cosmos import CosmosClient, PartitionKey  # type: ignore

        client = CosmosClient(az.cosmos_url, credential=az.cosmos_key)
        db = client.create_database_if_not_exists("lastmile")
        self._alerts = db.create_container_if_not_exists("alerts", PartitionKey(path="/id"))
        self._renders = db.create_container_if_not_exists("renders", PartitionKey(path="/id"))
        self._audio = db.create_container_if_not_exists("audio", PartitionKey(path="/id"))

    @staticmethod
    def _safe_id(raw: str) -> str:
        # Cosmos ids may not contain / \ # ?
        return raw.replace("/", "_").replace("\\", "_").replace("#", "_").replace("?", "_")

    def put_alert(self, alert_id: str, doc: dict) -> None:
        self._alerts.upsert_item({**doc, "id": self._safe_id(alert_id), "_alert_id": alert_id})

    def get_alert(self, alert_id: str) -> dict | None:
        try:
            item = self._alerts.read_item(self._safe_id(alert_id), self._safe_id(alert_id))
            return dict(item)
        except Exception:
            return None

    def list_alerts(self, limit: int = 200) -> list[dict]:
        q = f"SELECT TOP {int(limit)} * FROM c ORDER BY c.properties.sent DESC"
        return [dict(i) for i in self._alerts.query_items(q, enable_cross_partition_query=True)]

    def put_render(self, render_id: str, doc: dict) -> None:
        self._renders.upsert_item({**doc, "id": self._safe_id(render_id)})

    def get_render(self, render_id: str) -> dict | None:
        try:
            return dict(self._renders.read_item(self._safe_id(render_id), self._safe_id(render_id)))
        except Exception:
            return None

    def put_audio(self, render_id: str, lang: str, blob: bytes, mime: str) -> None:
        import base64

        key = self._safe_id(f"{render_id}:{lang}")
        self._audio.upsert_item(
            {"id": key, "mime": mime, "b64": base64.b64encode(blob).decode()}
        )

    def get_audio(self, render_id: str, lang: str) -> tuple[bytes, str] | None:
        import base64

        key = self._safe_id(f"{render_id}:{lang}")
        try:
            item = self._audio.read_item(key, key)
            return base64.b64decode(item["b64"]), item["mime"]
        except Exception:
            return None


_STORE: Store | None = None


def get_store() -> Store:
    global _STORE
    if _STORE is None:
        if config.AZURE.cosmos_url and config.AZURE.cosmos_key and not config.OFFLINE:
            try:  # pragma: no cover - deploy target
                _STORE = CosmosStore()
            except Exception:
                _STORE = SqliteStore()
        else:
            _STORE = SqliteStore()
    return _STORE


def set_store(store: Store) -> None:
    """Test hook."""
    global _STORE
    _STORE = store
