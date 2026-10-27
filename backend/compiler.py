"""Validate model output before any checklist can enter the application."""

from pydantic import ValidationError

from backend import meta_client
from backend.schemas import Checklist


class CompilerUnavailableError(Exception):
    """The configured real compiler has no verified API adapter yet."""


class InvalidChecklistError(Exception):
    """The model or fixture returned a checklist outside the contract."""

    def __init__(self, errors: list[dict]) -> None:
        super().__init__("The compiler returned an invalid checklist.")
        self.errors = errors


def compile_checklist(pdf_bytes: bytes) -> Checklist:
    try:
        result = meta_client.compile_manual(pdf_bytes)
    except NotImplementedError as error:
        raise CompilerUnavailableError from error

    try:
        return Checklist.model_validate(result)
    except ValidationError as error:
        # Do not return model output, input documents, or exception context.
        errors = error.errors(include_input=False, include_context=False, include_url=False)
        raise InvalidChecklistError(errors) from error


# M8: the pending Wonder adapter must request visual primitives and JSON,
# then repair once with safe validation errors. Official references are in docs/.
