"""HTTP workflow tests: compile -> inspect -> judge -> locked state -> audited override."""

import asyncio
import base64
import io
import json
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest.mock import patch
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from PIL import Image

from backend import main, meta_client
from backend.state import AuditWriteError, SessionStore
from backend.tests.test_compiler import fixture, manual_pdf
from backend.tests.test_judge import model_output


class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = SessionStore(Path(directory.name))
        for target, name, value in ((main.app.state, "session_store", self.store),
                                     (meta_client, "MOCK_MODE", True), (main, "MOCK_MODE", True)):
            patcher = patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test")
        self.addAsyncCleanup(self.client.aclose)
        buffer = io.BytesIO()
        Image.new("RGB", (640, 480)).save(buffer, format="PNG")
        self.frame = base64.b64encode(buffer.getvalue()).decode()
        self.session_id = await self.create_session()

    async def create_session(self, value=None, reviewed=True):
        with patch.object(meta_client, "compile_manual", return_value=value or fixture()):
            response = await self.client.post("/compile-manual", files={"file": ("manual.pdf", manual_pdf(), "application/pdf")})
        self.assertEqual(response.status_code, 200)
        session_id = response.headers["x-stepguard-session-id"]
        if reviewed:
            acknowledged = await self.client.post(f"/session/{session_id}/review")
            self.assertEqual(acknowledged.status_code, 200)
        return session_id

    async def verify(self, step_id=1, frame=None, session_id=None):
        return await self.client.post("/verify-step", json={
            "session_id": session_id or self.session_id, "step_id": step_id,
            "image_base64": self.frame if frame is None else frame,
        })

    async def override(self, step_id=1, reason="Manually checked for the development test."):
        return await self.client.post("/override", json={"session_id": self.session_id, "step_id": step_id, "reason": reason})

    async def snapshot(self):
        response = await self.client.get(f"/session/{self.session_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        return response.json()

    async def test_compile_creates_a_mock_session_with_only_first_step_active(self):
        snapshot = await self.snapshot()
        self.assertTrue(snapshot["mock_mode"])
        self.assertEqual([step["status"] for step in snapshot["steps"]], ["ACTIVE", "LOCKED"])
        self.assertEqual(snapshot["checklist"], fixture())

    async def test_unreviewed_session_rejects_checks_and_overrides_before_model_calls(self):
        self.session_id = await self.create_session(reviewed=False)
        self.assertIsNone((await self.snapshot())["reviewed_at"])
        with patch.object(meta_client, "segment") as segment:
            self.assertEqual((await self.verify()).status_code, 409)
            self.assertEqual((await self.override()).status_code, 409)
        segment.assert_not_called()
        reviewed = await self.client.post(f"/session/{self.session_id}/review")
        self.assertEqual(reviewed.status_code, 200)
        self.assertTrue(reviewed.json()["reviewed_at"])
        self.assertEqual(reviewed.headers["cache-control"], "no-store")
        self.assertEqual((await self.client.post(f"/session/{self.session_id}/review")).json(), reviewed.json())
        self.assertEqual((await self.verify()).status_code, 200)

    async def test_review_save_failure_keeps_start_gate_closed(self):
        self.session_id = await self.create_session(reviewed=False)
        with patch.object(self.store, "_persist", side_effect=AuditWriteError):
            response = await self.client.post(f"/session/{self.session_id}/review")
        self.assertEqual(response.status_code, 503)
        self.assertIsNone((await self.snapshot())["reviewed_at"])
        self.assertEqual((await self.verify()).status_code, 409)

    async def test_default_mock_check_is_unsure_and_next_step_remains_locked(self):
        response = await self.verify()
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["verdict"], "unsure")
        self.assertFalse(result["next_step_unlocked"])
        self.assertEqual(response.headers["x-stepguard-mode"], "MOCK")
        self.assertGreaterEqual(result["latency_ms"], 0)
        self.assertEqual([step["status"] for step in (await self.snapshot())["steps"]], ["UNSURE", "LOCKED"])

    async def test_locked_step_returns_409_before_any_segmentation_call(self):
        with patch.object(meta_client, "segment") as segment:
            response = await self.verify(2)
        self.assertEqual(response.status_code, 409)
        segment.assert_not_called()

    async def test_three_test_only_passes_advance_in_order_and_complete_the_session(self):
        value = fixture()
        value["steps"].append({**deepcopy(value["steps"][1]), "step_id": 3})
        self.session_id = await self.create_session(value)
        with patch.object(meta_client, "judge", return_value=model_output()):
            for step_id in (1, 2, 3):
                response = await self.verify(step_id)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["verdict"], "pass")
                self.assertEqual(response.json()["next_step_unlocked"], step_id < 3)
        snapshot = await self.snapshot()
        self.assertTrue(snapshot["complete"])
        self.assertTrue(all(step["passed_via"] == "automatic" for step in snapshot["steps"]))
        self.assertEqual((await self.verify(1)).status_code, 409)

    async def test_count_failure_blocks_step_three_even_when_model_claims_pass(self):
        value = fixture()
        value["steps"].append({**deepcopy(value["steps"][1]), "step_id": 3})
        self.session_id = await self.create_session(value)
        await self.override()
        segments = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "segments.json").read_text())
        segments["black pin"].pop()
        with patch.object(meta_client, "segment", side_effect=lambda image, prompt: deepcopy(segments[prompt])), \
                patch.object(meta_client, "judge", return_value=model_output()):
            response = await self.verify(2)
        self.assertEqual(response.json()["verdict"], "fail")
        self.assertIn("1 black pin missing", response.json()["message"])
        self.assertEqual([step["status"] for step in (await self.snapshot())["steps"]], ["PASSED", "FAILED", "LOCKED"])

    async def test_unsure_can_be_rechecked_then_pass_without_client_state_changes(self):
        await self.verify()
        with patch.object(meta_client, "judge", return_value=model_output()):
            response = await self.verify()
        self.assertEqual(response.json()["verdict"], "pass")
        self.assertTrue(response.json()["next_step_unlocked"])

    async def test_override_is_distinct_from_a_model_pass_and_audits_reason(self):
        await self.verify()
        response = await self.override(reason="Supervisor inspected the assembly by hand.")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["passed_via"], "override")
        snapshot = await self.snapshot()
        self.assertEqual(snapshot["steps"][0]["last_verdict"], "unsure")
        self.assertEqual(snapshot["steps"][1]["status"], "ACTIVE")
        event = next(event for event in snapshot["audit_log"] if event["event"] == "override")
        self.assertEqual(event["details"]["reason"], "Supervisor inspected the assembly by hand.")
        self.assertTrue(event["timestamp"].endswith("+00:00"))

    async def test_blank_override_and_locked_override_cannot_advance(self):
        self.assertEqual((await self.override(reason="  ")).status_code, 422)
        self.assertEqual((await self.override(2)).status_code, 409)
        self.assertEqual([step["status"] for step in (await self.snapshot())["steps"]], ["ACTIVE", "LOCKED"])

    async def test_invalid_image_is_logged_and_restores_active_for_retry(self):
        response = await self.verify(frame=base64.b64encode(b"not an image").decode())
        self.assertEqual(response.status_code, 400)
        snapshot = await self.snapshot()
        self.assertEqual(snapshot["steps"][0]["status"], "ACTIVE")
        self.assertEqual(snapshot["audit_log"][-1]["details"], {"code": "invalid_image"})

    async def test_bad_base64_is_rejected_before_starting_a_check(self):
        for frame in ("not base64!", "data:image/png;base64," + self.frame):
            with self.subTest(frame=frame[:20]):
                self.assertEqual((await self.verify(frame=frame)).status_code, 400)
        self.assertEqual(len((await self.snapshot())["audit_log"]), 3)

    async def test_request_validation_does_not_echo_private_camera_input(self):
        response = await self.client.post("/verify-step", json={
            "session_id": self.session_id, "step_id": True,
            "image_base64": {"private-camera-input": "private-frame-content"},
        })
        self.assertEqual(response.status_code, 422)
        self.assertNotIn("private-camera-input", response.text)
        self.assertNotIn("private-frame-content", response.text)

    async def test_client_cannot_supply_a_verdict(self):
        response = await self.client.post("/verify-step", json={
            "session_id": self.session_id, "step_id": 1, "image_base64": self.frame, "verdict": "pass",
        })
        self.assertEqual(response.status_code, 422)
        self.assertEqual((await self.snapshot())["steps"][0]["status"], "ACTIVE")

    async def test_unknown_sessions_steps_and_invalid_session_ids_are_rejected(self):
        self.assertEqual((await self.verify(session_id=str(uuid4()))).status_code, 404)
        self.assertEqual((await self.verify(99)).status_code, 404)
        self.assertEqual((await self.client.get(f"/session/{uuid4()}")).status_code, 404)
        self.assertEqual((await self.client.get("/session/not-a-uuid")).status_code, 422)

    async def test_unimplemented_real_adapter_returns_503_and_no_fixture_fallback(self):
        with patch.object(meta_client, "MOCK_MODE", False), patch.object(meta_client, "_fixture") as fixture_loader:
            response = await self.verify()
        self.assertEqual(response.status_code, 503)
        fixture_loader.assert_not_called()
        self.assertEqual((await self.snapshot())["steps"][0]["status"], "ACTIVE")

    async def test_unexpected_judge_error_does_not_leak_credentials_or_strand_checking(self):
        with patch.object(meta_client, "judge", side_effect=RuntimeError("private-api-key-example")):
            response = await self.verify()
        self.assertEqual(response.status_code, 502)
        snapshot = await self.snapshot()
        self.assertNotIn("private-api-key-example", response.text + json.dumps(snapshot))
        self.assertEqual(snapshot["steps"][0]["status"], "ACTIVE")

    async def test_invalid_judge_output_becomes_unsure_and_remains_locked(self):
        with patch.object(meta_client, "judge", return_value={"invalid": "private-result"}):
            response = await self.verify()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["verdict"], "unsure")
        self.assertFalse(response.json()["next_step_unlocked"])
        self.assertNotIn("private-result", response.text)

    async def test_disk_write_failure_before_check_returns_503_without_inspection(self):
        with patch.object(self.store, "_persist", side_effect=AuditWriteError), patch.object(meta_client, "segment") as segment:
            response = await self.verify()
        self.assertEqual(response.status_code, 503)
        segment.assert_not_called()
        self.assertEqual((await self.snapshot())["steps"][0]["status"], "ACTIVE")

    async def test_disk_write_failure_after_pass_does_not_unlock_the_next_step(self):
        persist = self.store._persist
        def fail_completion(session):
            if any(event.event == "check_completed" for event in session.audit_log):
                raise AuditWriteError
            persist(session)
        with patch.object(self.store, "_persist", side_effect=fail_completion), \
                patch.object(meta_client, "judge", return_value=model_output()):
            response = await self.verify()
        self.assertEqual(response.status_code, 503)
        snapshot = await self.snapshot()
        self.assertEqual([step["status"] for step in snapshot["steps"]], ["ACTIVE", "LOCKED"])
        self.assertFalse(any(event["event"] == "check_completed" for event in snapshot["audit_log"]))

    async def test_failed_override_audit_does_not_unlock(self):
        with patch.object(self.store, "_persist", side_effect=AuditWriteError):
            response = await self.override()
        self.assertEqual(response.status_code, 503)
        self.assertEqual([step["status"] for step in (await self.snapshot())["steps"]], ["ACTIVE", "LOCKED"])

    async def test_a_concurrent_check_and_override_are_rejected_while_checking(self):
        entered = asyncio.Event()
        release = Event()
        loop = asyncio.get_running_loop()
        def slow_judge(*args):
            loop.call_soon_threadsafe(entered.set)
            if not release.wait(5):
                raise RuntimeError("Test synchronization timed out")
            return model_output()
        with patch.object(meta_client, "judge", side_effect=slow_judge):
            first = asyncio.create_task(self.verify())
            try:
                await asyncio.wait_for(entered.wait(), 5)
                self.assertEqual((await self.snapshot())["steps"][0]["status"], "CHECKING")
                self.assertEqual((await self.verify()).status_code, 409)
                self.assertEqual((await self.override()).status_code, 409)
            finally:
                release.set()
                completed = await first
        self.assertEqual(completed.json()["verdict"], "pass")

    async def test_audit_has_no_original_frame_or_mask_payloads(self):
        response = await self.verify()
        self.assertEqual(response.status_code, 200)
        path = self.store.directory / f"{self.session_id}.json"
        saved = path.read_text()
        self.assertNotIn(self.frame, saved)
        self.assertNotIn("image_base64", saved)
        self.assertNotIn("mask_png_base64", saved)
        result = next(event for event in json.loads(saved)["audit_log"] if event["event"] == "check_completed")
        self.assertEqual(result["details"]["result"]["verdict"], "unsure")
