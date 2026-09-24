import json
from datetime import datetime, timedelta, timezone

from api.protocol import AzureTableContinuityStore


class FakeTable:
    def __init__(self):
        self.entities = {}

    def upsert_entity(self, entity):
        self.entities[(entity["PartitionKey"], entity["RowKey"])] = entity

    def get_entity(self, partition_key, row_key):
        return self.entities[(partition_key, row_key)]

    def delete_entity(self, partition_key, row_key):
        self.entities.pop((partition_key, row_key), None)


def _packet(code="RBX-ABCDE"):
    return {"continuity": {"code": code}, "needs": ["temporary_housing"]}


def test_azure_table_continuity_round_trip_is_shared_by_clients():
    table = FakeTable()
    first_instance = AzureTableContinuityStore(table_client=table)
    second_instance = AzureTableContinuityStore(table_client=table)
    first_instance.save(_packet())

    assert second_instance.load("rbx-abcde") == _packet()
    stored = table.entities[("continuity", "RBX-ABCDE")]
    assert json.loads(stored["packet_json"])["needs"] == ["temporary_housing"]


def test_expired_azure_table_packet_is_removed():
    table = FakeTable()
    table.entities[("continuity", "RBX-ABCDE")] = {
        "PartitionKey": "continuity",
        "RowKey": "RBX-ABCDE",
        "packet_json": json.dumps(_packet()),
        "expires_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
    }
    store = AzureTableContinuityStore(table_client=table)

    assert store.load("RBX-ABCDE") is None
    assert table.entities == {}
