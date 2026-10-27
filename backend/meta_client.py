"""Stable model boundary: mocks, the temporary Gemini demo, and future Meta calls.

The public call signatures follow the build prompt. Gemini is a temporary demo
provider authorized separately; Meta adapters still require M7–M10 integration.
No API key, model identifier, or endpoint is sent to clients or written to logs.
"""

import json
import os
from pathlib import Path
from typing import NoReturn

from dotenv import load_dotenv
from backend.model_errors import ModelError

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")


def _env_bool(name: str, default: str) -> bool:
    value = os.getenv(name, default).strip().lower()
    if value not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false")
    return value == "true"


MOCK_MODE = _env_bool("MOCK_MODE", "true")
META_API_KEY = os.getenv("META_API_KEY", "")
META_BASE_URL = os.getenv("META_BASE_URL", "")
MODEL_WONDER = os.getenv("MODEL_WONDER", "")
MODEL_SPARK = os.getenv("MODEL_SPARK", "")
MODEL_SAM = os.getenv("MODEL_SAM", "")
MODEL_VOICE = os.getenv("MODEL_VOICE", "")
MODEL_SPARK_OPEN = os.getenv("MODEL_SPARK_OPEN", "meta-models/muse-spark-open-1026")
BASELINE_URL = os.getenv("BASELINE_URL", "")
USE_OPEN_WEIGHTS = _env_bool("USE_OPEN_WEIGHTS", "false")
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "meta").strip().lower()
if MODEL_PROVIDER not in {"meta", "gemini"}:
    raise ValueError("MODEL_PROVIDER must be meta or gemini")


def adapters_ready() -> bool:
    if MODEL_PROVIDER == "gemini":
        from backend import gemini_client
        return gemini_client.ready()
    return False  # Meta adapters remain unimplemented; see docs/HACKATHON_READINESS.md.


def _fixture(name: str):
    # Reload on each call so callers never share mutable fixture data.
    return json.loads((Path(__file__).parent / "fixtures" / name).read_text())


def _require_adapter(operation: str) -> NoReturn:
    # Official API references are now recorded in docs/HACKATHON_READINESS.md.
    # Implementation and live validation must precede enabling these adapters.
    raise NotImplementedError(
        f"Real Meta {operation} is not implemented. "
        "Meta adapter implementation and validation are pending; use MOCK_MODE=true for development."
    )


def compile_manual(pdf_bytes: bytes) -> dict:
    """Muse Wonder: manual PDF to checklist (fixture in development)."""
    if MOCK_MODE:
        return _fixture("checklist.json")
    if MODEL_PROVIDER == "gemini":
        from backend import gemini_client
        return gemini_client.compile_manual(pdf_bytes)
    _require_adapter("manual compilation")


def segment(image_bytes: bytes, prompt: str) -> list[dict]:
    """SAM: part boxes and masks (fixture coordinates are image pixels)."""
    if MOCK_MODE:
        return _fixture("segments.json").get(prompt, [])
    if MODEL_PROVIDER == "gemini":
        from backend import gemini_client
        from backend.runtime import detection_cache
        identity = json.dumps(["gemini", gemini_client.GEMINI_MODEL, gemini_client.GEMINI_API_KEY])
        return detection_cache.get_or_call(identity, image_bytes, prompt,
                                            lambda: gemini_client.segment(image_bytes, prompt))
    _require_adapter("segmentation")


def judge(step: dict, found: dict, geometry: dict, annotated_image: bytes) -> dict:
    """Muse Spark: strict verdict JSON (development fixture is always unsure)."""
    if MOCK_MODE:
        return _fixture("judgment.json")
    if MODEL_PROVIDER == "gemini":
        from backend import gemini_client
        return gemini_client.judge(step, found, geometry, annotated_image)
    _require_adapter("judging")


def transcribe(audio_bytes: bytes, mime: str) -> str:
    """Muse Voice Transcribe: command text (fixture in development)."""
    if MOCK_MODE:
        return _fixture("transcription.json")["text"]
    if MODEL_PROVIDER == "gemini":
        from backend import gemini_client
        return gemini_client.transcribe(audio_bytes, mime)
    _require_adapter("transcription")


def baseline(step: dict, image_bytes: bytes) -> dict:
    """Evaluation only: plain visual judgment, without inspector evidence."""
    if MOCK_MODE:
        raise ModelError("Baseline evaluation requires real mode; fixtures are not evidence.", 503)
    if MODEL_PROVIDER == "gemini":
        from backend import gemini_client
        return gemini_client.baseline(step, image_bytes)
    _require_adapter("baseline evaluation")

