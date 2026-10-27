"""Portable workflow evidence; no media, secrets, or accuracy claims."""

from datetime import datetime, timezone

from backend.schemas import SessionView


def inspection_report(session: SessionView) -> dict:
    checks = [entry for entry in session.audit_log if entry.event == "check_completed"]
    return {
        "format_version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "evidence_label": "development fixtures" if session.mock_mode else "recorded provider outcomes",
        "limitations": [
            "Workflow counts are not a model accuracy estimate.",
            "Manual overrides are not automatic passes and do not authenticate a supervisor.",
            "This report excludes camera frames, masks, audio, and credentials.",
        ],
        "summary": {
            "total_steps": len(session.steps),
            "automatic_passes": sum(step.passed_via == "automatic" for step in session.steps),
            "manual_overrides": sum(step.passed_via == "override" for step in session.steps),
            "completed_checks": len(checks),
            "check_errors": sum(entry.event == "check_error" for entry in session.audit_log),
            "complete": session.complete,
        },
        "session": session.model_dump(mode="json"),
    }
