"""Sanitized errors shared by model adapters and the HTTP boundary."""


class ModelError(RuntimeError):
    def __init__(self, message: str, status: int = 502, *, retryable: bool = False):
        super().__init__(message)
        self.status = status
        self.retryable = retryable
