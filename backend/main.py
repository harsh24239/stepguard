"""Run from the repository root: python -m uvicorn backend.main:app --reload."""

import base64
import binascii
from pathlib import Path
from time import perf_counter
from typing import Annotated
from uuid import UUID

from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from backend.compiler import (
    CompilerUnavailableError,
    InvalidChecklistError,
    compile_checklist,
)
from backend.meta_client import MOCK_MODE
from backend import meta_client
from backend.model_errors import ModelError
from backend.runtime import CheckLimiter, observe_retries
from backend.inspector import InvalidImageError, inspect_step
from backend.judge import judge_step
from backend.schemas import (
    Checklist, OverrideRequest, OverrideResponse, SessionView, VerifyRequest, VerifyResponse,
)
from backend.state import (
    AuditWriteError, SessionNotFoundError, SessionStore, StepConflictError, StepNotFoundError,
)

MAX_MANUAL_BYTES = 10 * 1024 * 1024
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_AUDIO_BYTES = 5 * 1024 * 1024
AUDIO_TYPES = {"audio/webm", "audio/ogg", "audio/mp4", "audio/wav"}

app = FastAPI(
    title="StepGuard",
    description="Automatic assembly step checking prototype. M6: motion and voice triggers.",
    version="0.6.0",
)
app.state.session_store = SessionStore(Path(__file__).resolve().parent.parent / "sessions")
app.state.check_limiter = CheckLimiter()


@app.exception_handler(ModelError)
async def model_error_handler(request, error):
    return JSONResponse(status_code=error.status, content={"detail": str(error)})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request, error):
    # FastAPI's default can echo a rejected base64 camera frame in `input`.
    return JSONResponse(status_code=422, content={"detail": [
        {key: item[key] for key in ("loc", "msg", "type") if key in item}
        for item in error.errors()
    ]})


@app.exception_handler(SessionNotFoundError)
@app.exception_handler(StepNotFoundError)
async def not_found_handler(request, error):
    return JSONResponse(status_code=404, content={"detail": str(error)})


@app.exception_handler(StepConflictError)
async def conflict_handler(request, error):
    return JSONResponse(status_code=409, content={"detail": str(error)})


@app.exception_handler(AuditWriteError)
async def audit_error_handler(request, error):
    return JSONResponse(status_code=503, content={"detail": "The session audit could not be saved. Check storage and try again."})


def _response_headers(response: Response):
    response.headers["X-StepGuard-Mode"] = "MOCK" if MOCK_MODE else "LIVE"
    response.headers["X-StepGuard-Provider"] = meta_client.MODEL_PROVIDER
    response.headers["Cache-Control"] = "no-store"


class HealthResponse(BaseModel):
    status: str
    mock_mode: bool
    milestone: str
    model_adapters_ready: bool
    provider: str


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok", mock_mode=MOCK_MODE, milestone="M6", model_adapters_ready=meta_client.adapters_ready(),
        provider=meta_client.MODEL_PROVIDER,
    )


@app.post(
    "/compile-manual",
    response_model=Checklist,
    summary="Upload a PDF and return a validated assembly checklist",
    description=(
        "Upload a PDF of at most 10 MiB as multipart field `file`. "
        "In MOCK mode the response is a development fixture, independent of the PDF. "
        "PDF checks cover the header and media type, not full document parsing. "
        "The X-StepGuard-Mode response header identifies the execution mode."
        " A new session is created; X-StepGuard-Session-ID identifies it."
    ),
    responses={
        400: {"description": "Empty upload or missing PDF header"},
        413: {"description": "PDF exceeds the 10 MiB limit"},
        415: {"description": "Upload must have application/pdf media type"},
        502: {"description": "Compiler output failed checklist validation"},
        429: {"description": "Selected provider quota or rate limit reached"},
        503: {"description": "Selected model provider is unavailable or not configured"},
        504: {"description": "Selected model provider timed out"},
    },
)
async def compile_manual_endpoint(
    response: Response,
    file: Annotated[UploadFile, File(description="Assembly manual PDF (maximum 10 MiB)")],
) -> Checklist:
    try:
        media_type = (file.content_type or "").split(";", 1)[0].strip().lower()
        if media_type != "application/pdf":
            raise HTTPException(415, "Upload the manual with application/pdf media type.")
        pdf_bytes = await file.read(MAX_MANUAL_BYTES + 1)
        if len(pdf_bytes) > MAX_MANUAL_BYTES:
            raise HTTPException(413, "The manual must be 10 MiB or smaller.")
        if not pdf_bytes:
            raise HTTPException(400, "The uploaded manual is empty.")
        if not pdf_bytes.startswith(b"%PDF-"):
            raise HTTPException(400, "The uploaded file is missing a PDF header.")

        try:
            checklist = await run_in_threadpool(compile_checklist, pdf_bytes)
        except CompilerUnavailableError as error:
            raise HTTPException(
                503,
                "Real Meta manual compilation is not implemented yet. "
                "Use MOCK_MODE=true for development or the configured Gemini demo.",
            ) from error
        except InvalidChecklistError as error:
            raise HTTPException(
                502,
                {"message": "The compiler returned an invalid checklist.", "errors": error.errors},
            ) from error

        session = await run_in_threadpool(app.state.session_store.create, checklist, MOCK_MODE, meta_client.MODEL_PROVIDER)
        _response_headers(response)
        response.headers["X-StepGuard-Session-ID"] = session.session_id
        return checklist
    finally:
        await file.close()


@app.get("/session/{session_id}", response_model=SessionView)
def get_session(session_id: UUID, response: Response) -> SessionView:
    session = app.state.session_store.get(str(session_id))
    _response_headers(response)
    return session


@app.post("/session/{session_id}/review", response_model=SessionView,
          summary="Acknowledge compiled requirements before inspection")
def review_session(session_id: UUID, response: Response) -> SessionView:
    session = app.state.session_store.review(str(session_id))
    _response_headers(response)
    return session


class TranscriptionResponse(BaseModel):
    text: str
    mock_mode: bool


@app.post("/transcribe", response_model=TranscriptionResponse,
          summary="Transcribe a short audio clip without changing session state")
async def transcribe_audio(
    response: Response,
    file: Annotated[UploadFile, File(description="Audio clip, at most 5 MiB (WebM, Ogg, MP4, WAV)")],
) -> TranscriptionResponse:
    try:
        mime = (file.content_type or "").split(";", 1)[0].strip().lower()
        if mime not in AUDIO_TYPES:
            raise HTTPException(415, "Use audio/webm, audio/ogg, audio/mp4, or audio/wav.")
        audio = await file.read(MAX_AUDIO_BYTES + 1)
        if len(audio) > MAX_AUDIO_BYTES:
            raise HTTPException(413, "The audio clip must be 5 MiB or smaller.")
        if not audio:
            raise HTTPException(400, "The audio clip is empty. Hold the microphone button and try again.")
        # Basic container signatures only, not audio decoding or duration validation.
        signatures = {
            "audio/webm": audio.startswith(b"\x1a\x45\xdf\xa3"),
            "audio/ogg": audio.startswith(b"OggS"),
            "audio/mp4": len(audio) >= 12 and audio[4:8] == b"ftyp",
            "audio/wav": len(audio) >= 12 and audio[:4] == b"RIFF" and audio[8:12] == b"WAVE",
        }
        if not signatures[mime]:
            raise HTTPException(400, "The audio container does not match its media type. Record a new clip.")
        try:
            text = await run_in_threadpool(meta_client.transcribe, audio, mime)
        except ModelError:
            raise
        except NotImplementedError:
            raise HTTPException(503, "Real Meta transcription is not implemented. Use MOCK_MODE=true for development.") from None
        except Exception:
            raise HTTPException(502, "Voice transcription failed. Try recording again or use Check step.") from None
        if not isinstance(text, str) or len(text) > 4000:
            raise HTTPException(502, "The transcription adapter returned an invalid response. Use Check step.")
        _response_headers(response)
        return TranscriptionResponse(text=text.strip(), mock_mode=MOCK_MODE)
    finally:
        await file.close()


@app.post("/verify-step", response_model=VerifyResponse)
def verify_step(request: VerifyRequest, response: Response) -> VerifyResponse:
    try:
        image_bytes = base64.b64decode(request.image_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "image_base64 must contain raw base64 image bytes, without a data URL.") from None
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "The camera image must be 10 MiB or smaller.")
    store = app.state.session_store
    token, step = store.begin_check(request.session_id, request.step_id)
    started = perf_counter()
    try:
        if not MOCK_MODE:
            app.state.check_limiter.reserve()
        with observe_retries(lambda: store.note_retry(request.session_id, request.step_id, token)):
            evidence = inspect_step(step, image_bytes)
            result = judge_step(step, evidence)
        result.latency_ms = max(0, round((perf_counter() - started) * 1000))
        result = store.finish_check(request.session_id, token, result)
    except Exception as error:
        if isinstance(error, ModelError):
            code, status, message = "provider_error", error.status, str(error)
        elif isinstance(error, InvalidImageError):
            code, status, message = "invalid_image", 400, "Supply a decodable camera image within the pixel limit."
        elif isinstance(error, NotImplementedError):
            code, status, message = "adapter_unavailable", 503, "Real Meta inspection adapters are not implemented. Use MOCK_MODE=true for development."
        elif isinstance(error, AuditWriteError):
            code, status, message = "audit_unavailable", 503, "The check could not be saved. Check storage and try again."
        else:
            code, status, message = "check_error", 502, "Step checking failed. Check this step again."
        store.abort_check(request.session_id, request.step_id, token, code)
        raise HTTPException(status, message) from None
    _response_headers(response)
    return result


@app.post("/override", response_model=OverrideResponse)
def override_step(request: OverrideRequest, response: Response) -> OverrideResponse:
    result = app.state.session_store.override(request.session_id, request.step_id, request.reason)
    _response_headers(response)
    return result

