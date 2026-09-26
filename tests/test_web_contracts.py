from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_citizen_ui_exposes_language_resume_accessibility_and_offline_controls():
    html = (ROOT / "web" / "grounded" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "web" / "grounded" / "assist.js").read_text(encoding="utf-8")

    for control in (
        'id="plan-form"',
        'id="resume-plan-form"',
        'id="fraud-form"',
        'id="run-chaos"',
    ):
        assert control in html

    assert "/api/packet" in script
    assert 'data-plan-download' in script
    assert 'data-plan-call' in script
    assert 'data-plan-sms' in script
    assert "/api/continue/" in script
    assert "sensitive handoff reason" in script
    assert "/api/calls/start" in script
    assert "/api/sms/send" in script
    assert "Your next three steps" in script
    assert "Historical replay:" in script
    assert "Technical verification details" in script
    assert "This is a referral" in script


def test_scope_notices_move_with_useful_information_and_leave_low_data_mode():
    for page in ("index.html", "alert.html"):
        html = (ROOT / "web" / "grounded" / page).read_text(encoding="utf-8")
        assert 'class="wh-ticker" role="note" aria-label=' in html
        assert html.count('class="wh-ticker-track"') == 1
        assert "Call 911 for immediate danger" in html
    css = (ROOT / "web" / "grounded" / "wh.css").read_text(encoding="utf-8")
    assert "@keyframes wh-ticker-scroll" in css
    assert "[data-lowdata] .wh-ticker { display: none; }" in css
    assert "prefers-reduced-motion: reduce" in css
