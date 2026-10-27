"""Test the audio HTTP boundary in process, with original audio and injected adapters."""
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import wave

from httpx import ASGITransport, AsyncClient

from backend import main, meta_client
from backend.state import SessionStore
from backend.tests.test_compiler import fixture
from backend.schemas import Checklist


def audio_wav():
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\0\0" * 1600)
    return buffer.getvalue()


class TranscriptionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = SessionStore(Path(self.directory.name))
        for target, name, value in [(main.app.state, "session_store", self.store), (main, "MOCK_MODE", True), (meta_client, "MOCK_MODE", True)]:
            patcher = patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()

    async def upload(self, audio=None, mime="audio/wav"):
        return await self.client.post("/transcribe", files={"file": ("command.wav", audio_wav() if audio is None else audio, mime)})

    async def test_mock_clip_returns_labeled_fixture_without_advancing_or_auditing(self):
        session = self.store.create(Checklist.model_validate(fixture()), True)
        before = self.store.get(session.session_id).model_dump()
        files_before = {path.name: path.read_bytes() for path in Path(self.directory.name).iterdir()}
        response = await self.upload()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"text": "step done", "mock_mode": True})
        self.assertEqual(response.headers["x-stepguard-mode"], "MOCK")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(self.store.get(session.session_id).model_dump(), before)
        self.assertEqual({path.name: path.read_bytes() for path in Path(self.directory.name).iterdir()}, files_before)

    async def test_audio_and_normalized_mime_reach_only_the_model_boundary(self):
        audio = b"\x1a\x45\xdf\xa3original synthetic container header"
        with patch.object(meta_client, "transcribe", return_value=" Check step. ") as adapter:
            response = await self.upload(audio, "audio/webm;codecs=opus")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["text"], "Check step.")
        adapter.assert_called_once_with(audio, "audio/webm")

    async def test_supported_container_headers_are_accepted(self):
        # Header-only probes test transport validation, not decodability or model support.
        cases = [("audio/webm", b"\x1a\x45\xdf\xa3"), ("audio/ogg", b"OggS"),
                 ("audio/mp4", b"\x00\x00\x00\x18ftypisom"), ("audio/wav", audio_wav())]
        for mime, audio in cases:
            with self.subTest(mime=mime):
                self.assertEqual((await self.upload(audio, mime)).status_code, 200)

    async def test_missing_empty_wrong_type_and_wrong_signature_are_rejected(self):
        with patch.object(meta_client, "transcribe") as adapter:
            self.assertEqual((await self.client.post("/transcribe")).status_code, 422)
            for audio, mime, status in [(b"", "audio/wav", 400), (audio_wav(), "text/plain", 415),
                                        (b"PRIVATE_AUDIO", "audio/webm", 400), (b"OggS", "audio/mp4", 400)]:
                response = await self.upload(audio, mime)
                self.assertEqual(response.status_code, status)
                self.assertNotIn("PRIVATE_AUDIO", response.text)
            adapter.assert_not_called()

    async def test_oversized_audio_is_rejected_before_transcription(self):
        with patch.object(meta_client, "transcribe") as adapter:
            response = await self.upload(b"OggS" + b"x" * main.MAX_AUDIO_BYTES, "audio/ogg")
            self.assertEqual(response.status_code, 413)
            adapter.assert_not_called()

    async def test_real_adapter_is_unavailable_without_fixture_fallback(self):
        with patch.object(meta_client, "MOCK_MODE", False), patch.object(meta_client, "_fixture") as load:
            response = await self.upload()
        self.assertEqual(response.status_code, 503)
        load.assert_not_called()

    async def test_invalid_or_failed_adapter_does_not_echo_private_content(self):
        for invalid in [None, {"text": "PRIVATE_AUDIO"}, "PRIVATE_AUDIO" * 1000]:
            with patch.object(meta_client, "transcribe", return_value=invalid):
                response = await self.upload()
            self.assertEqual(response.status_code, 502)
            self.assertNotIn("PRIVATE_AUDIO", response.text)
        with patch.object(meta_client, "transcribe", side_effect=RuntimeError("PRIVATE_KEY")):
            response = await self.upload()
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("PRIVATE_KEY", response.text)

    async def test_silence_may_return_empty_text_without_becoming_a_command(self):
        with patch.object(meta_client, "transcribe", return_value="  "):
            response = await self.upload()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["text"], "")

    async def test_upload_is_closed_after_rejection(self):
        from fastapi import HTTPException, Response, UploadFile
        from starlette.datastructures import Headers
        file = UploadFile(io.BytesIO(b"bad audio"), filename="private.wav", headers=Headers({"content-type": "audio/wav"}))
        with self.assertRaises(HTTPException):
            await main.transcribe_audio(Response(), file)
        self.assertTrue(file.file.closed)

    async def test_openapi_documents_audio_upload(self):
        spec = (await self.client.get("/openapi.json")).json()
        self.assertIn("multipart/form-data", spec["paths"]["/transcribe"]["post"]["requestBody"]["content"])


if __name__ == "__main__":
    unittest.main()
