"""Exercise the actual built UI and API together without a network or paid call."""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient

from backend import main, meta_client
from backend.production import create_app
from backend.state import SessionStore


async def check():
    if not main.MOCK_MODE or not meta_client.MOCK_MODE:
        raise SystemExit("Release smoke test requires MOCK_MODE=true. It never calls live providers.")
    with TemporaryDirectory() as temporary, patch.object(main.app.state, "session_store", SessionStore(Path(temporary))):
        async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://release") as client:
            page = await client.get("/")
            assert page.status_code == 200 and '<div id="root"></div>' in page.text
            assert (await client.get("/stepguard.svg")).status_code == 200
            assert (await client.get("/api/health")).json()["mock_mode"] is True
            assert (await client.get("/api/missing-route")).status_code == 404
            assert (await client.get("/.env")).status_code == 404
            sample = await client.post("/api/sample-session")
            sample.raise_for_status()
            session = sample.json()
            assert session["mock_mode"] and session["reviewed_at"] is None
            reviewed = await client.post(f'/api/session/{session["session_id"]}/review')
            reviewed.raise_for_status()
            report = await client.get(f'/api/session/{session["session_id"]}/report')
            report.raise_for_status()
            assert report.json()["evidence_label"] == "development fixtures"
            assert report.json()["summary"]["automatic_passes"] == 0
    print("Built UI, API routing, sample/review/report flow, and private-file exclusion passed (synthetic inputs).")


if __name__ == "__main__":
    asyncio.run(check())
