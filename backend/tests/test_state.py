"""Step transitions, concurrent attempts, and durable override provenance."""

import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from backend.schemas import Checklist, VerifyResponse
from backend.state import AuditWriteError, SessionNotFoundError, SessionStore, StepConflictError


def checklist():
    path = Path(__file__).resolve().parents[1] / "fixtures" / "checklist.json"
    return Checklist.model_validate(json.loads(path.read_text()))


def result(step_id, verdict="pass"):
    return VerifyResponse(step_id=step_id, verdict=verdict, confidence=.95,
                          found_counts={}, expected_counts={}, issues=[], masks=[],
                          message="Test result.", fix_hint="Test hint.")


class StateTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = SessionStore(Path(self.directory.name))
        self.session = self.store.create(checklist(), True)
        self.session_id = self.session.session_id
        self.store.review(self.session_id)

    def statuses(self):
        return [step.status for step in self.store.get(self.session_id).steps]

    def check(self, step_id, verdict):
        token, _ = self.store.begin_check(self.session_id, step_id)
        return self.store.finish_check(self.session_id, token, result(step_id, verdict))

    def test_new_session_locks_later_steps_and_persists_its_mode(self):
        self.assertEqual(self.statuses(), ["ACTIVE", "LOCKED"])
        path = Path(self.directory.name) / f"{self.session_id}.json"
        data = json.loads(path.read_text())
        self.assertTrue(data["mock_mode"])
        self.assertEqual(data["audit_log"][0]["event"], "session_created")

    def test_review_is_required_for_checks_and_overrides_and_is_idempotent(self):
        pending = self.store.create(checklist(), True)
        with self.assertRaisesRegex(StepConflictError, "Review"):
            self.store.begin_check(pending.session_id, 1)
        with self.assertRaisesRegex(StepConflictError, "Review"):
            self.store.override(pending.session_id, 1, "Cannot skip review")
        reviewed = self.store.review(pending.session_id)
        self.assertIsNotNone(reviewed.reviewed_at)
        self.assertEqual(self.store.review(pending.session_id), reviewed)
        self.assertEqual([entry.event for entry in reviewed.audit_log].count("requirements_reviewed"), 1)
        self.assertEqual([step.status for step in reviewed.steps], ["ACTIVE", "LOCKED"])

    def test_failed_review_save_does_not_enable_inspection(self):
        pending = self.store.create(checklist(), True)
        with patch.object(self.store, "_persist", side_effect=AuditWriteError):
            with self.assertRaises(AuditWriteError):
                self.store.review(pending.session_id)
        self.assertIsNone(self.store.get(pending.session_id).reviewed_at)
        with self.assertRaises(StepConflictError):
            self.store.begin_check(pending.session_id, 1)

    def test_failed_and_unsure_checks_keep_the_successor_locked(self):
        for verdict in ("fail", "unsure"):
            with self.subTest(verdict=verdict):
                response = self.check(1, verdict)
                self.assertFalse(response.next_step_unlocked)
                self.assertEqual(self.statuses(), [{"fail": "FAILED", "unsure": "UNSURE"}[verdict], "LOCKED"])

    def test_retry_then_pass_unlocks_only_the_successor(self):
        self.check(1, "fail")
        response = self.check(1, "pass")
        self.assertTrue(response.next_step_unlocked)
        self.assertEqual(self.statuses(), ["PASSED", "ACTIVE"])
        snapshot = self.store.get(self.session_id)
        self.assertEqual(snapshot.steps[0].passed_via, "automatic")
        self.assertTrue(any(event.event == "step_activated" and event.details.get("previous_status") == "FAILED"
                            for event in snapshot.audit_log))

    def test_final_pass_completes_session_without_claiming_another_unlock(self):
        self.check(1, "pass")
        self.assertFalse(self.check(2, "pass").next_step_unlocked)
        self.assertTrue(self.store.get(self.session_id).complete)

    def test_locked_passed_and_checking_steps_reject_checks(self):
        with self.assertRaises(StepConflictError):
            self.store.begin_check(self.session_id, 2)
        token, _ = self.store.begin_check(self.session_id, 1)
        with self.assertRaises(StepConflictError):
            self.store.begin_check(self.session_id, 1)
        self.store.finish_check(self.session_id, token, result(1))
        with self.assertRaises(StepConflictError):
            self.store.begin_check(self.session_id, 1)

    def test_stale_check_tokens_cannot_finish(self):
        self.store.begin_check(self.session_id, 1)
        with self.assertRaises(StepConflictError):
            self.store.finish_check(self.session_id, "stale-token", result(1))
        self.assertEqual(self.statuses(), ["CHECKING", "LOCKED"])

    def test_abort_restores_active_and_records_only_a_safe_error_code(self):
        token, _ = self.store.begin_check(self.session_id, 1)
        self.store.abort_check(self.session_id, 1, token, "adapter_unavailable")
        self.assertEqual(self.statuses(), ["ACTIVE", "LOCKED"])
        self.assertEqual(self.store.get(self.session_id).audit_log[-1].details, {"code": "adapter_unavailable"})

    def test_override_records_reason_time_and_preserves_last_model_verdict(self):
        self.check(1, "unsure")
        response = self.store.override(self.session_id, 1, "  Manually checked all four pins.  ")
        self.assertTrue(response.next_step_unlocked)
        snapshot = self.store.get(self.session_id)
        self.assertEqual(snapshot.steps[0].last_verdict, "unsure")
        self.assertEqual(snapshot.steps[0].passed_via, "override")
        event = next(event for event in snapshot.audit_log if event.event == "override")
        self.assertEqual(event.details["reason"], "Manually checked all four pins.")
        self.assertTrue(event.timestamp.endswith("+00:00"))
        saved = json.loads((Path(self.directory.name) / f"{self.session_id}.json").read_text())
        self.assertEqual(saved["steps"][0]["passed_via"], "override")

    def test_override_cannot_skip_locked_steps_or_interrupt_an_active_check(self):
        with self.assertRaises(StepConflictError):
            self.store.override(self.session_id, 2, "Skip ahead")
        self.store.begin_check(self.session_id, 1)
        with self.assertRaises(StepConflictError):
            self.store.override(self.session_id, 1, "Interrupt check")

    def test_empty_override_reason_is_rejected_without_mutating_state(self):
        with self.assertRaises(ValueError):
            self.store.override(self.session_id, 1, "  ")
        self.assertEqual(self.statuses(), ["ACTIVE", "LOCKED"])

    def test_failed_audit_write_cannot_commit_a_pass_or_override(self):
        with patch.object(self.store, "_persist", side_effect=AuditWriteError):
            with self.assertRaises(AuditWriteError):
                self.store.override(self.session_id, 1, "Manually checked")
        self.assertEqual(self.statuses(), ["ACTIVE", "LOCKED"])
        token, _ = self.store.begin_check(self.session_id, 1)
        with patch.object(self.store, "_persist", side_effect=AuditWriteError):
            with self.assertRaises(AuditWriteError):
                self.store.finish_check(self.session_id, token, result(1))
            with self.assertRaises(AuditWriteError):
                self.store.abort_check(self.session_id, 1, token, "audit_unavailable")
        self.assertEqual(self.statuses(), ["ACTIVE", "LOCKED"])
        self.assertTrue(self.check(1, "pass").next_step_unlocked)

    def test_actual_atomic_write_failure_does_not_replace_existing_audit(self):
        path = Path(self.directory.name) / f"{self.session_id}.json"
        previous = path.read_bytes()
        with patch("backend.state.os.replace", side_effect=OSError("disk unavailable")):
            with self.assertRaises(AuditWriteError):
                self.store.override(self.session_id, 1, "Manually checked")
        self.assertEqual(path.read_bytes(), previous)
        self.assertEqual(list(Path(self.directory.name).glob(".audit-*")), [])

    def test_snapshots_do_not_share_mutable_state(self):
        snapshot = self.store.get(self.session_id)
        snapshot.steps[1].status = "PASSED"
        snapshot.checklist.steps[0].instruction = "changed"
        self.assertEqual(self.statuses(), ["ACTIVE", "LOCKED"])
        self.assertNotEqual(self.store.get(self.session_id).checklist.steps[0].instruction, "changed")

    def test_only_one_concurrent_check_can_start(self):
        def attempt(_):
            try:
                return self.store.begin_check(self.session_id, 1)[0]
            except StepConflictError:
                return None
        with ThreadPoolExecutor(max_workers=8) as executor:
            tokens = list(executor.map(attempt, range(16)))
        self.assertEqual(sum(token is not None for token in tokens), 1)
        self.assertEqual(self.statuses(), ["CHECKING", "LOCKED"])

    def test_audit_excludes_camera_masks(self):
        token, _ = self.store.begin_check(self.session_id, 1)
        response = result(1)
        from backend.schemas import OverlayMask
        response.masks = [OverlayMask(label="pin", box=(1., 1., 2., 2.), status="ok", mask_png_base64="PRIVATE_MASK_CONTENT")]
        self.store.finish_check(self.session_id, token, response)
        saved = (Path(self.directory.name) / f"{self.session_id}.json").read_text()
        self.assertNotIn("PRIVATE_MASK_CONTENT", saved)
        self.assertNotIn("mask_png_base64", saved)

    def test_sessions_are_independent_and_unknown_ids_are_rejected(self):
        other = self.store.create(checklist(), True)
        self.store.override(self.session_id, 1, "Manually checked")
        self.assertEqual([step.status for step in self.store.get(other.session_id).steps], ["ACTIVE", "LOCKED"])
        with self.assertRaises(SessionNotFoundError):
            self.store.get("not-a-session")
