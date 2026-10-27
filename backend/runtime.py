"""Bounded model retries, transient progress, and local cost controls.

Only operation names, timings, and status codes are logged. Media, prompts,
keys, model responses, and exception strings never enter these logs.
"""

from collections import OrderedDict, deque
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
import hashlib
import json
import logging
import os
from threading import RLock
import time

from backend.model_errors import ModelError

logger = logging.getLogger("stepguard.models")
_retry_observer = ContextVar("stepguard_retry_observer", default=None)


def setting(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        raise ValueError(f"{name} must be an integer") from None
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


@contextmanager
def observe_retries(callback):
    token = _retry_observer.set(callback)
    try:
        yield
    finally:
        _retry_observer.reset(token)


def model_call(provider: str, operation: str, invoke):
    retries = setting("MODEL_MAX_RETRIES", 2, 0, 2)
    for attempt in range(retries + 1):
        started = time.monotonic()
        status = 200
        try:
            return invoke()
        except ModelError as error:
            status = error.status
            if not error.retryable or attempt == retries:
                raise
            observer = _retry_observer.get()
            if observer:
                observer()
            time.sleep(.5 * 2 ** attempt)
        except Exception:
            status = 500
            raise
        finally:
            logger.info("provider=%s operation=%s attempt=%d status=%d latency_ms=%d",
                        provider, operation, attempt + 1, status,
                        round((time.monotonic() - started) * 1000))


class CheckLimiter:
    """Rolling global limit for this single-process local prototype."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self._times = deque()
        self._lock = RLock()

    def reserve(self):
        limit = setting("MAX_CHECKS_PER_MINUTE", 10, 1, 120)
        with self._lock:
            now = self.clock()
            while self._times and self._times[0] <= now - 60:
                self._times.popleft()
            if len(self._times) >= limit:
                raise ModelError("Check limit reached. Wait up to one minute before checking again.", 429)
            self._times.append(now)


class DetectionCache:
    """Short-lived, bounded detection evidence; never cache a step verdict.

The lock also prevents concurrent identical requests from issuing duplicate
provider calls. Bytes are hashed, and only normalized detections live in RAM.
"""

    def __init__(self, clock=time.monotonic, max_bytes=16 * 1024 * 1024, max_entries=64):
        self.clock, self.max_bytes, self.max_entries = clock, max_bytes, max_entries
        self._entries = OrderedDict()
        self._bytes = 0
        self._lock = RLock()

    def clear(self):
        with self._lock:
            self._entries.clear()
            self._bytes = 0

    def get_or_call(self, identity: str, image: bytes, prompt: str, invoke):
        ttl = setting("DETECTION_CACHE_SECONDS", 30, 0, 300)
        if not ttl:
            return invoke()
        key = hashlib.sha256(json.dumps([identity, prompt]).encode() + b"\0" + image).digest()
        with self._lock:
            now = self.clock()
            for old_key, (expires, _, size) in list(self._entries.items()):
                if expires <= now:
                    del self._entries[old_key]
                    self._bytes -= size
            if key in self._entries:
                expires, result, size = self._entries.pop(key)
                self._entries[key] = (expires, result, size)
                return deepcopy(result)
            result = invoke()  # Exceptions are never cached.
            size = len(json.dumps(result, allow_nan=False).encode())
            if size <= self.max_bytes:
                while self._entries and (self._bytes + size > self.max_bytes or len(self._entries) >= self.max_entries):
                    _, (_, _, removed) = self._entries.popitem(last=False)
                    self._bytes -= removed
                self._entries[key] = (self.clock() + ttl, deepcopy(result), size)
                self._bytes += size
            return result


detection_cache = DetectionCache()
