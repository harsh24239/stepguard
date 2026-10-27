"""In-memory sessions with serialized transitions and atomic JSON audit snapshots."""

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4

from backend.schemas import (
    AuditEntry, Checklist, ChecklistStep, OverrideResponse, SessionStep, SessionView, VerifyResponse,
)


class SessionNotFoundError(Exception):
    pass


class StepNotFoundError(Exception):
    pass


class StepConflictError(Exception):
    pass


class AuditWriteError(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event(session: SessionView, event: str, step_id=None, **details):
    session.audit_log.append(AuditEntry(timestamp=_now(), event=event, step_id=step_id, details=details))


class SessionStore:
    """One backend process owns sessions. Audit files are evidence, not a database."""

    def __init__(self, directory: Path):
        self.directory = directory
        self._sessions: dict[str, SessionView] = {}
        self._tokens: dict[str, str] = {}
        self._lock = RLock()

    def _persist(self, session: SessionView):
        temporary = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", dir=self.directory, prefix=".audit-", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(session.model_dump_json(indent=2))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.directory / f"{session.session_id}.json")
        except OSError as error:
            raise AuditWriteError("Session audit could not be written.") from error
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass  # Cleanup must not replace the primary audit-write error.

    def _commit(self, session: SessionView):
        self._persist(session)
        self._sessions[session.session_id] = session

    def _copy(self, session_id: str) -> SessionView:
        try:
            return self._sessions[session_id].model_copy(deep=True)
        except KeyError:
            raise SessionNotFoundError("Session not found; compile a manual to start one.") from None

    def _step(self, session: SessionView, step_id: int) -> SessionStep:
        if not 1 <= step_id <= len(session.steps):
            raise StepNotFoundError("Step not found in this session.")
        return session.steps[step_id - 1]

    def create(self, checklist: Checklist, mock_mode: bool, provider: str = "meta") -> SessionView:
        with self._lock:
            session = SessionView(
                session_id=str(uuid4()), created_at=_now(), mock_mode=mock_mode, provider=provider,
                checklist=checklist.model_copy(deep=True),
                steps=[SessionStep(step_id=step.step_id, status="ACTIVE" if index == 0 else "LOCKED")
                       for index, step in enumerate(checklist.steps)], audit_log=[],
            )
            _event(session, "session_created", mock_mode=mock_mode, provider=provider)
            _event(session, "step_activated", 1, previous_status="LOCKED")
            self._commit(session)
            return session.model_copy(deep=True)

    def get(self, session_id: str) -> SessionView:
        with self._lock:
            return self._copy(session_id)

    def review(self, session_id: str) -> SessionView:
        """Acknowledge the immutable compiled requirements; retries are idempotent."""
        with self._lock:
            session = self._copy(session_id)
            if session.reviewed_at is None:
                session.reviewed_at = _now()
                _event(session, "requirements_reviewed")
                self._commit(session)
            return session.model_copy(deep=True)

    def _require_review(self, session: SessionView):
        if session.reviewed_at is None:
            raise StepConflictError("Review the extracted requirements and start inspection first.")

    def begin_check(self, session_id: str, step_id: int) -> tuple[str, ChecklistStep]:
        with self._lock:
            session = self._copy(session_id)
            step = self._step(session, step_id)
            self._require_review(session)
            if step.status not in {"ACTIVE", "FAILED", "UNSURE"}:
                raise StepConflictError("This step is locked, already passed, or being checked.")
            if any(previous.status != "PASSED" for previous in session.steps[:step_id - 1]):
                raise StepConflictError("Earlier steps must pass before this step can be checked.")
            if step.status != "ACTIVE":
                _event(session, "step_activated", step_id, previous_status=step.status)
                step.status = "ACTIVE"
            step.status = "CHECKING"
            step.retry_count = 0
            _event(session, "check_started", step_id)
            token = str(uuid4())
            self._commit(session)
            self._tokens[session_id] = token
            return token, session.checklist.steps[step_id - 1].model_copy(deep=True)

    def _checking(self, session_id: str, step_id: int, token: str) -> tuple[SessionView, SessionStep]:
        session = self._copy(session_id)
        step = self._step(session, step_id)
        if self._tokens.get(session_id) != token or step.status != "CHECKING":
            raise StepConflictError("This check is no longer current.")
        return session, step

    def note_retry(self, session_id: str, step_id: int, token: str):
        """Transient progress; verdict commits still require an atomic audit write."""
        with self._lock:
            session, step = self._checking(session_id, step_id, token)
            step.retry_count += 1
            self._sessions[session_id] = session

    def _advance(self, session: SessionView, step_id: int) -> bool:
        if step_id == len(session.steps):
            session.complete = True
            return False
        successor = session.steps[step_id]
        successor.status = "ACTIVE"
        _event(session, "step_activated", successor.step_id, previous_status="LOCKED")
        return True

    def finish_check(self, session_id: str, token: str, result: VerifyResponse) -> VerifyResponse:
        with self._lock:
            session, step = self._checking(session_id, result.step_id, token)
            result = result.model_copy(deep=True)
            step.status = {"pass": "PASSED", "fail": "FAILED", "unsure": "UNSURE"}[result.verdict]
            step.last_verdict = result.verdict
            step.passed_via = "automatic" if result.verdict == "pass" else None
            result.next_step_unlocked = result.verdict == "pass" and result.step_id < len(session.steps)
            _event(session, "check_completed", result.step_id,
                   result=result.model_dump(mode="json", exclude={"masks"}))
            if result.verdict == "pass":
                self._advance(session, result.step_id)
            self._commit(session)
            self._tokens.pop(session_id, None)
            return result

    def abort_check(self, session_id: str, step_id: int, token: str, code: str):
        with self._lock:
            session, step = self._checking(session_id, step_id, token)
            step.status = "ACTIVE"
            _event(session, "check_error", step_id, code=code)
            try:
                self._commit(session)
            except AuditWriteError:
                # A failed check must not strand CHECKING or unlock anything. Keep
                # the safe recovery state in memory; the endpoint reports 503.
                self._sessions[session_id] = session
                raise
            finally:
                self._tokens.pop(session_id, None)

    def override(self, session_id: str, step_id: int, reason: str) -> OverrideResponse:
        reason = reason.strip()
        if not reason or len(reason) > 1000:
            raise ValueError("An override requires a reason of 1–1000 characters.")
        with self._lock:
            session = self._copy(session_id)
            step = self._step(session, step_id)
            self._require_review(session)
            if step.status not in {"ACTIVE", "FAILED", "UNSURE"}:
                raise StepConflictError("Only the current, idle step can be overridden.")
            if any(previous.status != "PASSED" for previous in session.steps[:step_id - 1]):
                raise StepConflictError("Earlier steps must pass first.")
            previous_status = step.status
            step.status = "PASSED"
            step.passed_via = "override"
            _event(session, "override", step_id, reason=reason, previous_status=previous_status,
                   last_verdict=step.last_verdict, passed_via="override")
            unlocked = self._advance(session, step_id)
            self._commit(session)
            return OverrideResponse(session_id=session_id, step_id=step_id, reason=reason,
                                    next_step_unlocked=unlocked)
