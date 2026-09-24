import json
from pathlib import Path

from function_app import app


def test_azure_functions_exposes_http_timer_and_sms_event_routes():
    names = {function.get_function_name() for function in app.get_functions()}
    assert names == {"http_app", "ingest_nws", "sms_event"}


def test_azure_functions_preserves_fastapi_route_contract():
    host = json.loads((Path(__file__).parents[1] / "host.json").read_text(encoding="utf-8"))
    assert host["extensions"]["http"]["routePrefix"] == ""
