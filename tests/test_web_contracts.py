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


def test_freshness_labels_remain_explicit_across_accessibility_modes():
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    styles = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
    assert "SOURCE REVIEW NEEDED" in script
    assert "Source review required before relying on time-sensitive details." in script
    assert 'class="freshness-warning" role="note"' in script
    for selector in (
        "body.large-text .freshness-pill",
        "body.high-contrast .freshness-pill",
        "body.high-contrast .freshness-pill.stale",
        "body.low-data .freshness-warning",
    ):
        assert selector in styles


def test_source_conflict_replaces_normal_confidence_with_visible_warning():
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    styles = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
    assert "Official sources disagree." in script
    assert "Conflict detected — verify before acting." in script
    assert 'class="source-conflict-warning" role="alert"' in script
    assert 'program.source_conflict?.detected ? "conflict"' in script
    assert 'program.source_conflict?.detected ? "Verify with official source"' in script
    assert ".confidence-pill.conflict" in styles
    assert ".recommendation-card.has-source-conflict" in styles


def test_evidence_text_is_escaped_and_reviewed_links_are_hardened():
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    for expression in (
        "escapeHtml(program.evidence?.rule)",
        "escapeHtml(program.evidence?.source_excerpt)",
        'escapeHtml(program.evidence?.last_reviewed || "Not recorded")',
        "escapeHtml(program.evidence?.caveat)",
    ):
        assert expression in script
    assert 'href="${escapeHtml(program.source_url)}" target="_blank" rel="noopener"' in script
    assert 'href="${escapeHtml(program.source_conflict?.detected ? program.source_url : program.apply_url)}" target="_blank" rel="noopener"' in script
