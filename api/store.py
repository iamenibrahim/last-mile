from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Protocol

from .config import settings


ROOT = Path(__file__).resolve().parents[1]


class RenderStore(Protocol):
    def save_render(self, result: dict) -> None: ...


class SQLiteRenderStore:
    """Local alert/render cache. Citizen navigation profiles are never stored here."""

    def __init__(self, path: Path | None = None):
        self.path = path or ROOT / "data" / "last_mile.db"
        self._lock = Lock()
        self._prepare()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=4)

    def _prepare(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS renders (
                    signature TEXT PRIMARY KEY,
                    cap_id TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )

    def save_render(self, result: dict) -> None:
        manifest = result["manifest"]
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO renders(signature, cap_id, source_sha256, payload_json) VALUES (?, ?, ?, ?)",
                (
                    manifest["signature"],
                    manifest["source"]["cap_id"],
                    manifest["source"]["sha256"],
                    json.dumps(result, ensure_ascii=False),
                ),
            )


class CosmosRenderStore:
    """Cosmos DB adapter, imported lazily so the offline demo has no Azure dependency."""

    def __init__(self):
        from azure.cosmos import CosmosClient, PartitionKey  # type: ignore
        from azure.identity import DefaultAzureCredential  # type: ignore

        client = CosmosClient(settings.cosmos_endpoint, credential=DefaultAzureCredential())
        database = client.create_database_if_not_exists("last-mile")
        self.container = database.create_container_if_not_exists(
            id="renders", partition_key=PartitionKey(path="/cap_id")
        )

    def save_render(self, result: dict) -> None:
        manifest = result["manifest"]
        self.container.upsert_item(
            {
                "id": manifest["signature"],
                "cap_id": manifest["source"]["cap_id"],
                "source_sha256": manifest["source"]["sha256"],
                "result": result,
            }
        )


def create_store() -> RenderStore:
    if settings.cosmos_endpoint:
        try:
            return CosmosRenderStore()
        except Exception:
            pass
    return SQLiteRenderStore()

