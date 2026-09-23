"""ACS B16004 × alert archive impact-analysis entry point.

This intentionally refuses to emit a population estimate without downloaded,
dated source data. See docs/evaluation.md for the production procedure.
"""

from __future__ import annotations


def require_source_data(alert_archive: str | None, acs_export: str | None) -> None:
    if not alert_archive or not acs_export:
        raise SystemExit(
            "Impact estimate not run: provide a dated NWS alert archive and ACS B16004 export. "
            "The project will not fabricate the hackathon impact number."
        )


if __name__ == "__main__":
    require_source_data(None, None)

