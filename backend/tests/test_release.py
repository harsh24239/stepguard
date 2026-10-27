"""Test sample onboarding, export provenance, and the single-origin built release."""

import base64
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient

from backend import main, meta_client
from backend.production import create_app
from backend.state import AuditWriteError, SessionStore


class ReleaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.store = SessionStore(self.root / "sessions")
        for target, name, value in [(main.app.state, "session_store", self.store), (main, "MOCK_MODE", True), (meta_client, "MOCK_MODE", True)]:
            current = patch.object(target, name, value)
            current.start()
            self.addCleanup(current.stop)
        static = self.root / "static"
        (static / "assets").mkdir(parents=True)
        (static / "index.html").write_text('<html><div id="root"></div></html>')
        (static / "assets/app.js").write_text("// Original test fixture")
        (self.root / ".env").write_text("PRIVATE_CONFIGURATION_CONTENT")
        self.production = create_app(static)
        self.client = AsyncClient(transport=ASGITransport(app=self.production), base_url="http://test")
        self.addAsyncCleanup(self.client.aclose)

    async def sample(self):
        response = await self.client.post("/api/sample-session")
        self.assertEqual(response.status_code, 200)
        return response.json()

    async def test_sample_is_a_fresh_labeled_fixture_that_still_requires_review(self):
        with patch.object(meta_client, "_require_adapter", side_effect=AssertionError("No live calls")):
            sample = await self.sample()
        self.assertTrue(sample["mock_mode"])
        self.assertIsNone(sample["reviewed_at"])
        self.assertEqual([step["status"] for step in sample["steps"]], ["ACTIVE", "LOCKED"])
        response = await self.client.post("/api/override", json={"session_id": sample["session_id"], "step_id": 1, "reason": "Cannot bypass review"})
        self.assertEqual(response.status_code, 409)

    async def test_live_mode_never_exposes_sample_or_falls_back_to_fixtures(self):
        for target in (main, meta_client):
            with patch.object(target, "MOCK_MODE", False), patch.object(main, "compile_checklist") as compile_manual:
                response = await self.client.post("/api/sample-session")
                self.assertEqual(response.status_code, 409)
                compile_manual.assert_not_called()

    async def test_failed_sample_save_returns_503_without_a_live_session(self):
        with patch.object(self.store, "_persist", side_effect=AuditWriteError):
            self.assertEqual((await self.client.post("/api/sample-session")).status_code, 503)
        self.assertEqual(self.store._sessions, {})

    async def test_export_preserves_review_and_override_provenance_without_mutating_state(self):
        sample = await self.sample()
        session_id = sample["session_id"]
        await self.client.post(f"/api/session/{session_id}/review")
        response = await self.client.post("/api/verify-step", json={"session_id": session_id, "step_id": 1, "image_base64": base64.b64encode(b"PRIVATE_FRAME_CONTENT").decode()})
        self.assertEqual(response.status_code, 400)
        await self.client.post("/api/override", json={"session_id": session_id, "step_id": 1, "reason": "Synthetic test: no actual assembly inspected."})
        before = self.store.get(session_id)
        report = await self.client.get(f"/api/session/{session_id}/report")
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.headers["cache-control"], "no-store")
        self.assertIn('attachment; filename="stepguard-', report.headers["content-disposition"])
        value = report.json()
        self.assertEqual(value["evidence_label"], "development fixtures")
        self.assertEqual(value["summary"], {"total_steps": 2, "automatic_passes": 0, "manual_overrides": 1, "completed_checks": 0, "check_errors": 1, "complete": False})
        self.assertTrue(value["session"]["reviewed_at"])
        self.assertNotIn("PRIVATE_FRAME_CONTENT", report.text)
        self.assertNotIn("image_base64", report.text)
        self.assertNotIn("mask_png_base64", report.text)
        self.assertEqual(self.store.get(session_id), before)

    async def test_frontend_api_and_unknown_routes_are_separate(self):
        self.assertIn('id="root"', (await self.client.get("/")).text)
        asset = await self.client.get("/assets/app.js")
        self.assertEqual(asset.status_code, 200)
        self.assertEqual(asset.headers["x-content-type-options"], "nosniff")
        self.assertEqual((await self.client.get("/api/health")).status_code, 200)
        response = await self.client.get("/api/not-a-route")
        self.assertEqual(response.status_code, 404)
        self.assertIn("application/json", response.headers["content-type"])
        self.assertNotIn('id="root"', response.text)
        self.assertEqual((await self.client.get("/tests/preview.html")).status_code, 404)

    async def test_static_host_never_serves_project_configuration_or_path_traversal(self):
        for path in ("/.env", "/%2e%2e/.env", "/backend/meta_client.py", "/sessions/test.json"):
            response = await self.client.get(path)
            self.assertEqual(response.status_code, 404)
            self.assertNotIn("PRIVATE_CONFIGURATION_CONTENT", response.text)

    async def test_missing_build_fails_with_actionable_setup_message(self):
        with self.assertRaisesRegex(RuntimeError, "npm run build"):
            create_app(self.root / "not-built")
