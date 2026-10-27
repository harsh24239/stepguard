"""Gemini REST contracts and complete pipeline using intercepted HTTP only.

All responses and images here are test-authored, never real model evidence.
"""

import base64
from contextlib import ExitStack
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx
from PIL import Image

from backend import gemini_client as gemini, main, meta_client
from backend.model_errors import ModelError
from backend.state import SessionStore
from backend.runtime import CheckLimiter, detection_cache
from backend.tests.test_compiler import fixture, manual_pdf
from backend.tests.test_judge import model_output
from backend.tests.test_transcribe import audio_wav
from scripts.day1_sam_test import evaluate

HTTP_CLIENT = httpx.Client


def response(value, **changes):
    return {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(value)}]}, **changes}]}


def png():
    output = io.BytesIO()
    Image.new("RGB", (640, 480), "#26313a").save(output, format="PNG")
    return output.getvalue()


def transport_patch(handler):
    transport = httpx.MockTransport(handler)
    def client(**kwargs):
        return HTTP_CLIENT(transport=transport, **kwargs)
    return patch.object(gemini.httpx, "Client", side_effect=client)


class GeminiAdapterTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, {"MODEL_MAX_RETRIES": "0", "DETECTION_CACHE_SECONDS": "0"}))
        self.stack.enter_context(patch.object(gemini, "GEMINI_API_KEY", "TEST_PRIVATE_KEY"))
        self.stack.enter_context(patch.object(gemini, "GEMINI_MODEL", "gemini-test-model"))

    def generate(self, body, status=200):
        with transport_patch(lambda request: httpx.Response(status, json=body)):
            return gemini._generate("Test instruction", {"text": "data"}, {"type": "object"})

    def test_missing_key_or_invalid_model_fails_before_network(self):
        for key, model in [("", "gemini-test"), ("key", "../other?key=PRIVATE"), ("key", "")]:
            with patch.object(gemini, "GEMINI_API_KEY", key), patch.object(gemini, "GEMINI_MODEL", model), patch.object(gemini.httpx, "Client") as client:
                self.assertFalse(gemini.ready())
                with self.assertRaises(ModelError) as raised:
                    gemini.compile_manual(manual_pdf())
                self.assertEqual(raised.exception.status, 503)
                client.assert_not_called()

    def test_rest_request_keeps_key_out_of_url_and_uses_documented_schema(self):
        def handler(request):
            self.assertEqual(str(request.url), "https://generativelanguage.googleapis.com/v1beta/models/gemini-test-model:generateContent")
            self.assertEqual(request.headers["x-goog-api-key"], "TEST_PRIVATE_KEY")
            self.assertNotIn("TEST_PRIVATE_KEY", str(request.url))
            body = json.loads(request.content)
            self.assertEqual(body["contents"], [{"role": "user", "parts": [{"text": "data"}]}])
            self.assertEqual(body["generationConfig"]["responseMimeType"], "application/json")
            self.assertEqual(body["generationConfig"]["responseJsonSchema"], {"type": "object"})
            self.assertIn("untrusted data", body["systemInstruction"]["parts"][0]["text"])
            self.assertEqual(request.extensions["timeout"]["read"], 30)
            return httpx.Response(200, json=response({"ok": True}))
        with transport_patch(handler):
            self.assertEqual(gemini._generate("instruction", {"text": "data"}, {"type": "object"}), {"ok": True})

    def test_auth_quota_missing_model_and_service_errors_are_sanitized(self):
        for status, expected in [(401, 503), (403, 503), (404, 503), (429, 429), (400, 502), (500, 502), (302, 502)]:
            with self.subTest(status=status), self.assertRaises(ModelError) as raised:
                self.generate({"error": "TEST_PRIVATE_KEY PRIVATE_IMAGE"}, status)
            self.assertEqual(raised.exception.status, expected)
            self.assertNotIn("TEST_PRIVATE_KEY", str(raised.exception))
            self.assertNotIn("PRIVATE_IMAGE", str(raised.exception))

    def test_network_and_timeout_errors_are_sanitized_and_never_retried(self):
        for error, expected in [(httpx.ReadTimeout("TEST_PRIVATE_KEY"), 504), (httpx.ConnectError("PRIVATE_IMAGE"), 503)]:
            calls = []
            def handler(request):
                calls.append(request)
                raise error
            with transport_patch(handler), self.assertRaises(ModelError) as raised:
                gemini.compile_manual(manual_pdf())
            self.assertEqual(raised.exception.status, expected)
            self.assertEqual(len(calls), 1)
            self.assertNotIn("PRIVATE", str(raised.exception))

    def test_blocked_truncated_and_malformed_responses_cannot_be_used(self):
        cases = [{}, [], {"candidates": []}, {"candidates": [None]},
                 response({"ok": True}, finishReason="SAFETY"), response({"ok": True}, finishReason="MAX_TOKENS"),
                 response({"ok": True}, content={"parts": [{"text": "PRIVATE_IMAGE"}]}), response([])]
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ModelError) as raised:
                self.generate(value)
            self.assertNotIn("PRIVATE_IMAGE", str(raised.exception))

    def test_thought_parts_are_not_parsed_as_the_model_answer(self):
        body = response({}, content={"parts": [{"thought": True, "text": "PRIVATE_THOUGHT"}, {"text": '{"text":'}, {"text": '"step done"}'}]})
        self.assertEqual(self.generate(body), {"text": "step done"})

    def test_pdf_is_sent_inline_with_cumulative_visual_checklist_instructions(self):
        def handler(request):
            body = json.loads(request.content)
            inline = body["contents"][0]["parts"][0]["inlineData"]
            self.assertEqual(inline["mimeType"], "application/pdf")
            self.assertEqual(base64.b64decode(inline["data"]), manual_pdf())
            instruction = body["systemInstruction"]["parts"][0]["text"]
            self.assertIn("cumulative", instruction)
            self.assertIn("not serial numbers", instruction)
            return httpx.Response(200, json=response(fixture()))
        with transport_patch(handler):
            self.assertEqual(gemini.compile_manual(manual_pdf()), fixture())

    def test_normalized_yx_boxes_become_xy_pixel_boxes_without_fabricated_masks(self):
        value = {"detections": [{"box_2d": [125, 125, 875, 875], "confidence": .92}]}
        def handler(request):
            body = json.loads(request.content)
            self.assertIn('"yellow plate"', body["systemInstruction"]["parts"][0]["text"])
            inline = body["contents"][0]["parts"][0]["inlineData"]
            self.assertEqual(inline["mimeType"], "image/png")
            self.assertTrue(base64.b64decode(inline["data"]).startswith(b"\x89PNG"))
            return httpx.Response(200, json=response(value))
        with transport_patch(handler):
            result = gemini.segment(png(), "yellow plate")
        self.assertEqual(result, [{"label": "yellow plate", "box": [80., 60., 560., 420.], "score": .92, "mask_png_base64": ""}])

    def test_no_detections_is_empty_without_fixture_fallback(self):
        with transport_patch(lambda request: httpx.Response(200, json=response({"detections": []}))), patch.object(meta_client, "_fixture") as load:
            self.assertEqual(gemini.segment(png(), "yellow plate"), [])
        load.assert_not_called()

    def test_invalid_detection_coordinates_confidence_and_structure_are_rejected(self):
        cases = [{}, {"detections": None}, {"detections": [None]}, {"detections": [{"box_2d": [0, 0, 1, 1]}]},
                 {"detections": [{"box_2d": [0, 0, 100, 100], "confidence": .9, "extra": True}]}]
        for box in [[0, 0, 1001, 500], [0, 10, 100, 10], [0, 0, float("nan"), 1], [True, 0, 100, 100], [0, 0, 100]]:
            cases.append({"detections": [{"box_2d": box, "confidence": .9}]})
        for score in [True, -1, 2, "0.9", float("inf")]:
            cases.append({"detections": [{"box_2d": [0, 0, 100, 100], "confidence": score}]})
        for value in cases:
            with self.subTest(value=value), patch.object(gemini, "_generate", return_value=value), self.assertRaises(ModelError):
                gemini.segment(png(), "plate")

    def test_invalid_image_never_reaches_gemini(self):
        with patch.object(gemini, "_generate") as generate, self.assertRaises(ModelError):
            gemini.segment(b"PRIVATE_IMAGE", "plate")
        generate.assert_not_called()

    def test_judge_receives_image_and_geometry_and_validates_output(self):
        value = model_output()
        def handler(request):
            body = json.loads(request.content)
            self.assertIn('"counts_match": false', body["systemInstruction"]["parts"][0]["text"])
            self.assertIn("Never override a count", body["systemInstruction"]["parts"][0]["text"])
            self.assertEqual(body["contents"][0]["parts"][0]["inlineData"]["mimeType"], "image/png")
            return httpx.Response(200, json=response(value))
        with transport_patch(handler):
            self.assertEqual(gemini.judge({}, {}, {"counts_match": False}, png()), value)
        with patch.object(gemini, "_generate", return_value={"verdict": "pass", "confidence": 2}):
            self.assertEqual(gemini.judge({}, {}, {}, png()), {})

    def test_audio_transcription_preserves_silence_and_actual_words(self):
        for text in ["", "step done", "do not check step"]:
            def handler(request):
                inline = json.loads(request.content)["contents"][0]["parts"][0]["inlineData"]
                self.assertEqual(inline["mimeType"], "audio/webm")
                self.assertEqual(base64.b64decode(inline["data"]), b"AUDIO")
                return httpx.Response(200, json=response({"text": text}))
            with transport_patch(handler):
                self.assertEqual(gemini.transcribe(b"AUDIO", "audio/webm"), text)

    def test_browser_mp4_audio_uses_the_documented_m4a_mime(self):
        with patch.object(gemini, "_generate", return_value={"text": "step done"}) as generate:
            gemini.transcribe(b"AUDIO", "audio/mp4")
        self.assertEqual(generate.call_args.args[1]["inlineData"]["mimeType"], "audio/m4a")

    def test_invalid_transcript_and_unsupported_audio_are_rejected(self):
        for value in [{}, {"text": []}, {"text": "x" * 4001}, {"text": "step done", "extra": 1}]:
            with patch.object(gemini, "_generate", return_value=value), self.assertRaises(ModelError):
                gemini.transcribe(b"AUDIO", "audio/webm")
        with patch.object(gemini, "_generate") as generate, self.assertRaises(ModelError):
            gemini.transcribe(b"AUDIO", "text/plain")
        generate.assert_not_called()

    def test_explicit_provider_routes_all_operations_and_mock_always_takes_precedence(self):
        calls = [("compile_manual", (manual_pdf(),)), ("segment", (png(), "yellow plate")),
                 ("judge", ({}, {}, {}, png())), ("transcribe", (audio_wav(), "audio/wav"))]
        for operation, args in calls:
            with patch.object(meta_client, "MODEL_PROVIDER", "gemini"), patch.object(meta_client, "MOCK_MODE", False), patch.object(gemini, operation, return_value="DELEGATED") as adapter:
                self.assertEqual(getattr(meta_client, operation)(*args), "DELEGATED")
                adapter.assert_called_once_with(*args)
            with patch.object(meta_client, "MODEL_PROVIDER", "gemini"), patch.object(meta_client, "MOCK_MODE", True), patch.object(gemini, operation) as adapter:
                getattr(meta_client, operation)(*args)
                adapter.assert_not_called()

    def test_sam_gate_rejects_gemini_as_meta_evidence(self):
        with patch.object(meta_client, "MODEL_PROVIDER", "gemini"), patch.object(meta_client, "MOCK_MODE", False), patch.object(gemini, "segment") as adapter:
            with self.assertRaisesRegex(ValueError, "cannot establish a SAM result"):
                evaluate(png(), ["one", "two", "three", "four", "five"])
        adapter.assert_not_called()


class GeminiWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = SessionStore(Path(self.directory.name))
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, {"MODEL_MAX_RETRIES": "0", "DETECTION_CACHE_SECONDS": "0"}))
        self.stack.enter_context(patch.object(main.app.state, "check_limiter", CheckLimiter()))
        for target, name, value in [(main.app.state, "session_store", self.store),
                                    (main, "MOCK_MODE", False), (meta_client, "MOCK_MODE", False),
                                    (meta_client, "MODEL_PROVIDER", "gemini"),
                                    (gemini, "GEMINI_API_KEY", "TEST_PRIVATE_KEY"), (gemini, "GEMINI_MODEL", "gemini-test")]:
            self.stack.enter_context(patch.object(target, name, value))
        self.posts = []
        self.error_status = None
        self.pin_count = 4
        self.invalid_judge = False
        def handler(request):
            self.posts.append(request)
            if self.error_status:
                return httpx.Response(self.error_status, json={"private": "TEST_PRIVATE_KEY"})
            body = json.loads(request.content)
            instruction = body["systemInstruction"]["parts"][0]["text"]
            if instruction.startswith("Read this assembly manual"):
                value = fixture()
            elif instruction.startswith("Detect every visible instance"):
                if '"yellow plate"' in instruction:
                    boxes = [[125, 125, 875, 875]]
                else:
                    boxes = [[210, 200, 260, 240], [210, 760, 260, 800], [720, 200, 770, 240], [720, 760, 770, 800]][:self.pin_count]
                value = {"detections": [{"box_2d": box, "confidence": .95} for box in boxes]}
            elif instruction.startswith("Assess the current assembly"):
                value = {} if self.invalid_judge else model_output()
            else:
                value = {"text": "step done"}
            return httpx.Response(200, json=response(value))
        self.stack.enter_context(transport_patch(handler))
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test")
        self.addAsyncCleanup(self.client.aclose)

    async def compile(self):
        result = await self.client.post("/compile-manual", files={"file": ("original.pdf", manual_pdf(), "application/pdf")})
        self.assertEqual(result.status_code, 200, result.text)
        session_id = result.headers["x-stepguard-session-id"]
        self.assertEqual((await self.client.post(f"/session/{session_id}/review")).status_code, 200)
        return session_id

    async def verify(self, session, step):
        return await self.client.post("/verify-step", json={"session_id": session, "step_id": step, "image_base64": base64.b64encode(png()).decode()})

    async def test_live_demo_compiles_checks_and_records_provider_without_fixtures(self):
        with patch.object(meta_client, "_fixture", side_effect=AssertionError("Fixtures must not be loaded")):
            health = (await self.client.get("/health")).json()
            self.assertEqual(health["provider"], "gemini")
            self.assertTrue(health["model_adapters_ready"])
            session = await self.compile()
            for step in (1, 2):
                checked = await self.verify(session, step)
                self.assertEqual(checked.status_code, 200, checked.text)
                self.assertEqual(checked.json()["verdict"], "pass")
                self.assertEqual(checked.headers["x-stepguard-provider"], "gemini")
            snapshot = (await self.client.get(f"/session/{session}")).json()
            self.assertTrue(snapshot["complete"])
            self.assertEqual(snapshot["provider"], "gemini")
            self.assertFalse(snapshot["mock_mode"])
            audit = json.loads((Path(self.directory.name) / f"{session}.json").read_text())
            self.assertEqual(audit["audit_log"][0]["details"]["provider"], "gemini")
            self.assertNotIn("TEST_PRIVATE_KEY", json.dumps(audit))
            self.assertNotIn("mask_png_base64", json.dumps(audit))

    async def test_missing_part_blocks_progress_despite_gemini_pass(self):
        session = await self.compile()
        self.assertEqual((await self.verify(session, 1)).json()["verdict"], "pass")
        self.pin_count = 3
        checked = (await self.verify(session, 2)).json()
        self.assertEqual(checked["verdict"], "fail")
        self.assertIn("1 black pin missing", checked["message"])
        snapshot = (await self.client.get(f"/session/{session}")).json()
        self.assertFalse(snapshot["complete"])
        self.assertEqual(snapshot["steps"][1]["status"], "FAILED")

    async def test_invalid_judge_remains_unsure_and_next_step_locked(self):
        session = await self.compile()
        self.invalid_judge = True
        checked = (await self.verify(session, 1)).json()
        self.assertEqual(checked["verdict"], "unsure")
        self.assertFalse(checked["next_step_unlocked"])
        self.assertEqual((await self.verify(session, 2)).status_code, 409)

    async def test_provider_error_recovers_current_step_without_unlocking(self):
        session = await self.compile()
        self.error_status = 429
        checked = await self.verify(session, 1)
        self.assertEqual(checked.status_code, 429)
        self.assertNotIn("TEST_PRIVATE_KEY", checked.text)
        snapshot = (await self.client.get(f"/session/{session}")).json()
        self.assertEqual([item["status"] for item in snapshot["steps"]], ["ACTIVE", "LOCKED"])

    async def test_compiler_error_creates_no_session_and_has_safe_http_response(self):
        self.error_status = 403
        result = await self.client.post("/compile-manual", files={"file": ("original.pdf", manual_pdf(), "application/pdf")})
        self.assertEqual(result.status_code, 503)
        self.assertNotIn("TEST_PRIVATE_KEY", result.text)
        self.assertEqual(list(Path(self.directory.name).iterdir()), [])

    async def test_real_audio_endpoint_is_labeled_and_does_not_mutate_a_session(self):
        session = await self.compile()
        before = self.store.get(session).model_dump()
        result = await self.client.post("/transcribe", files={"file": ("original.wav", audio_wav(), "audio/wav")})
        self.assertEqual(result.json(), {"text": "step done", "mock_mode": False})
        self.assertEqual(result.headers["x-stepguard-provider"], "gemini")
        self.assertEqual(self.store.get(session).model_dump(), before)
        self.error_status = 429
        result = await self.client.post("/transcribe", files={"file": ("original.wav", audio_wav(), "audio/wav")})
        self.assertEqual(result.status_code, 429)

    async def test_configured_without_a_key_is_not_reported_ready(self):
        with patch.object(gemini, "GEMINI_API_KEY", ""):
            health = (await self.client.get("/health")).json()
            self.assertFalse(health["model_adapters_ready"])
            self.assertFalse(health["mock_mode"])
            self.assertEqual(health["provider"], "gemini")

    async def test_check_limit_recovers_current_step_without_another_provider_call(self):
        session = await self.compile()
        with patch.dict(os.environ, {"MAX_CHECKS_PER_MINUTE": "1"}):
            self.assertEqual((await self.verify(session, 1)).status_code, 200)
            before = len(self.posts)
            blocked = await self.verify(session, 2)
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(len(self.posts), before)
        self.assertEqual(self.store.get(session).steps[1].status, "ACTIVE")

    async def test_transient_retry_is_visible_in_session_without_unlocking_ahead(self):
        session = await self.compile()
        original = gemini._generate_once
        observed = []
        def intermittent(*args):
            if not observed:
                observed.append(True)
                raise ModelError("temporary", 503, retryable=True)
            progress = self.store.get(session)
            self.assertEqual(progress.steps[0].status, "CHECKING")
            self.assertEqual(progress.steps[0].retry_count, 1)
            self.assertEqual(progress.steps[1].status, "LOCKED")
            return original(*args)
        with patch.dict(os.environ, {"MODEL_MAX_RETRIES": "1"}), patch('backend.runtime.time.sleep'), patch.object(gemini, '_generate_once', side_effect=intermittent):
            result = await self.verify(session, 1)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.store.get(session).steps[0].retry_count, 1)
        self.assertEqual(self.store.get(session).steps[1].status, "ACTIVE")


if __name__ == "__main__":
    unittest.main()
