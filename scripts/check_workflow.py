"""Exercise the HTTP workflow in process, using original MOCK assets and real audit writes."""

import argparse
import asyncio
import base64
import io
import json
import wave

from httpx import ASGITransport, AsyncClient
from PIL import Image

from backend import meta_client
from backend.main import app


def synthetic_pdf() -> bytes:
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Contents 4 0 R >>",
               b"<< /Length 0 >>\nstream\n\nendstream"]
    document, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, 1):
        offsets.append(len(document))
        document += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    position = len(document)
    document += b"xref\n0 5\n0000000000 65535 f \n"
    document += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    return document + f"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n{position}\n%%EOF\n".encode()


async def exercise(include_override: bool, include_voice: bool = False):
    image = io.BytesIO()
    Image.new("RGB", (640, 480), "#121a23").save(image, format="PNG")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        compiled = await client.post("/compile-manual", files={"file": ("synthetic.pdf", synthetic_pdf(), "application/pdf")})
        compiled.raise_for_status()
        session_id = compiled.headers["x-stepguard-session-id"]
        reviewed = await client.post(f"/session/{session_id}/review")
        reviewed.raise_for_status()
        transcription = None
        if include_voice:
            audio = io.BytesIO()
            with wave.open(audio, "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(16000)
                output.writeframes(b"\0\0" * 1600)
            before = (await client.get(f"/session/{session_id}")).json()
            transcribed = await client.post("/transcribe", files={"file": ("synthetic-silence.wav", audio.getvalue(), "audio/wav")})
            transcribed.raise_for_status()
            transcription = transcribed.json()
            assert transcription == {"text": "step done", "mock_mode": True}, "Voice must remain an explicitly labeled fixture"
            assert (await client.get(f"/session/{session_id}")).json() == before, "Transcription must not advance a step"
        request = {"session_id": session_id, "step_id": 1, "image_base64": base64.b64encode(image.getvalue()).decode()}
        checked = await client.post("/verify-step", json=request)
        checked.raise_for_status()
        result = checked.json()
        assert result["verdict"] == "unsure", "The default mock judge must stay unsure"
        blocked = await client.post("/verify-step", json={**request, "step_id": 2})
        assert blocked.status_code == 409, "Step 2 must stay locked"
        override_result = None
        if include_override:
            override = await client.post("/override", json={
                "session_id": session_id, "step_id": 1,
                "reason": "Development fixture workflow check: explicit manual override, not a model pass.",
            })
            override.raise_for_status()
            override_result = override.json()
        snapshot = await client.get(f"/session/{session_id}")
        snapshot.raise_for_status()
        print(json.dumps({
            "mode": compiled.headers["x-stepguard-mode"],
            "synthetic_inputs": True,
            "transcription": transcription,
            "session_id": session_id,
            "check": {key: result[key] for key in ("verdict", "message", "fix_hint", "next_step_unlocked", "latency_ms")},
            "locked_step_http_status": blocked.status_code,
            "override": override_result,
            "steps": snapshot.json()["steps"],
            "audit_file": str(app.state.session_store.directory / f"{session_id}.json"),
        }, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exercise-override", action="store_true", help="Also perform an explicit, logged development override")
    parser.add_argument("--exercise-voice", action="store_true", help="Also transcribe original synthetic silence through the mock audio endpoint")
    args = parser.parse_args()
    if not meta_client.MOCK_MODE:
        parser.error("This development check requires MOCK_MODE=true.")
    asyncio.run(exercise(args.exercise_override, args.exercise_voice))


if __name__ == "__main__":
    main()
