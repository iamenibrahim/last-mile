import subprocess

import pytest

from scripts.readiness_report import EXPECTED_SKIP, collect, exit_status, parse_pytest


def test_junit_counts_expected_skip_and_failures(tmp_path):
    path = tmp_path / "results.xml"
    path.write_text(f'''<testsuites><testsuite>
      <testcase name="pass"/>
      <testcase name="test_each_corruption_class_is_caught[swap_road]">
        <skipped message="{EXPECTED_SKIP}"/></testcase>
      <testcase name="unexpected"><skipped message="provider unavailable"/></testcase>
      <testcase name="failure"><failure message="secret must not be emitted"/></testcase>
      <testcase name="error"><error/></testcase>
    </testsuite></testsuites>''', encoding="utf-8")
    result = parse_pytest(path)
    assert (result["total"], result["passed"], result["failed"]) == (5, 1, 2)
    assert (result["skipped"], result["expected_skips"], result["unexpected_skips"]) == (2, 1, 1)
    assert "secret" not in str(result)


@pytest.mark.parametrize("required,status,expected", [
    (True, "passed", 0), (True, "failed", 1), (True, "unavailable", 1),
    (False, "unavailable", 0), (False, "failed", 1),
])
def test_exit_status_fails_required_checks_and_observed_telemetry_failures(required, status, expected):
    assert exit_status({"checks": [{"required": required, "status": status}]}) == expected


def test_failed_commands_never_disclose_diagnostic_output(monkeypatch):
    def unavailable(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "command", output="credential=private; +17035550123")

    monkeypatch.setattr("scripts.readiness_report.command", unavailable)
    report = collect()
    assert exit_status(report) == 1
    assert "credential" not in str(report)
    assert "17035550123" not in str(report)
    assert all("evidence" not in check or "private" not in str(check["evidence"]) for check in report["checks"])
