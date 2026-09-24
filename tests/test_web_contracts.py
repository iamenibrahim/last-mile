from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_citizen_ui_exposes_language_resume_accessibility_and_offline_controls():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

    for control in (
        'id="language-modal"',
        'id="resume-form"',
        'id="save-offline-plan"',
        'id="high-contrast"',
        'value="appeal_or_denied"',
        'value="fraud_concern"',
        'value="unsafe_shelter"',
        'value="complex_case"',
    ):
        assert control in html

    assert 'const OFFLINE_PACKET_KEY = "last-mile-signed-packet-v1"' in script
    assert "/api/continue/" in script
    assert "mode=citizen" in script
    assert "sensitive handoff reason" not in script
    assert 'data-start-call' in script
    assert 'id="call-consent"' in script
    assert "/api/calls/start" in script
    assert "# demo" in script


def test_service_worker_cache_version_changes_with_offline_contract():
    worker = (ROOT / "web" / "sw.js").read_text(encoding="utf-8")
    assert 'const CACHE = "last-mile-v2"' in worker
