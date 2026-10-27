"""Serve the built React app and the existing API from one local origin."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.main import app as api

ROOT = Path(__file__).resolve().parents[1]


def create_app(directory: Path | None = None) -> FastAPI:
    directory = directory or ROOT / "frontend" / "dist"
    if not (directory / "index.html").is_file():
        raise RuntimeError("Frontend build missing. Run npm run build in frontend/ first.")
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    # Mount API before static content: unknown API routes remain JSON 404s.
    app.mount("/api", api)
    app.mount("/", StaticFiles(directory=directory, html=True, follow_symlink=False), name="frontend")

    @app.middleware("http")
    async def response_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if not request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    return app
