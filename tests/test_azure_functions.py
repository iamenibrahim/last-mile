from function_app import app


def test_azure_functions_exposes_http_timer_and_sms_event_routes():
    names = {function.get_function_name() for function in app.get_functions()}
    assert names == {"http_app", "ingest_nws", "sms_event"}
