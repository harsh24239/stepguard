"""Exercise uploads and invalid checklists without live services or private assets."""

import json
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from backend import main, meta_client
from backend.compiler import InvalidChecklistError, compile_checklist
from backend.schemas import Checklist
from backend.state import SessionStore


def fixture() -> dict:
    path = Path(__file__).resolve().parents[1] / "fixtures" / "checklist.json"
    return json.loads(path.read_text())


def manual_pdf() -> bytes:
    """Create an original, one-page PDF in memory, including its cross-reference table."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Contents 4 0 R >>",
        b"<< /Length 0 >>\nstream\n\nendstream",
    ]
    document = b"%PDF-1.4\n"
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(document))
        document += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_position = len(document)
    document += b"xref\n0 5\n0000000000 65535 f \n"
    document += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    document += (
        f"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n{xref_position}\n%%EOF\n".encode()
    )
    return document


class ChecklistValidationTests(unittest.TestCase):
    def test_fixture_round_trips_without_changing_contract(self):
        value = fixture()
        self.assertEqual(Checklist.model_validate(value).model_dump(), value)

    def test_rejects_invalid_checklist_structure_and_references(self):
        def change_step(**changes):
            value = fixture()
            value["steps"][1].update(changes)
            return value

        extra_field = fixture()
        extra_field["unexpected"] = True
        cases = {
            "empty checklist": {"product": "Kit", "steps": []},
            "blank product": {**fixture(), "product": "  "},
            "unknown field": extra_field,
            "missing field": {"steps": fixture()["steps"]},
            "duplicate step ID": change_step(step_id=1),
            "skipped step ID": change_step(step_id=3),
            "boolean step ID": change_step(step_id=True),
            "blank instruction": change_step(instruction="  "),
            "duplicate prompt": change_step(sam_prompts=["yellow plate", "black pin", "black pin"]),
            "unknown anchor": change_step(zone_anchor="red beam"),
            "missing count": change_step(expected_counts={"yellow plate": 1}),
            "extra count": change_step(expected_counts={"yellow plate": 1, "black pin": 4, "wheel": 1}),
            "negative count": change_step(expected_counts={"yellow plate": 1, "black pin": -1}),
            "string count": change_step(expected_counts={"yellow plate": 1, "black pin": "4"}),
            "boolean count": change_step(expected_counts={"yellow plate": 1, "black pin": True}),
            "absent anchor": change_step(expected_counts={"yellow plate": 0, "black pin": 4}),
            "unknown spatial part": change_step(spatial_rules=[{"part": "wheel", "relation": "inside", "target": "yellow plate"}]),
            "unknown spatial target": change_step(spatial_rules=[{"part": "black pin", "relation": "inside", "target": "wheel"}]),
            "unknown relation": change_step(spatial_rules=[{"part": "black pin", "relation": "near", "target": "yellow plate"}]),
            "self relation": change_step(spatial_rules=[{"part": "black pin", "relation": "inside", "target": "black pin"}]),
        }
        for name, value in cases.items():
            with self.subTest(name=name), self.assertRaises(ValidationError):
                Checklist.model_validate(value)

    def test_zero_count_is_allowed_for_a_non_anchor_part(self):
        value = fixture()
        value["steps"][1]["expected_counts"]["black pin"] = 0
        self.assertEqual(Checklist.model_validate(value).steps[1].expected_counts["black pin"], 0)

    def test_compiler_passes_document_to_the_model_boundary(self):
        pdf = manual_pdf()
        with patch.object(meta_client, "compile_manual", return_value=fixture()) as compile_model:
            result = compile_checklist(pdf)
        compile_model.assert_called_once_with(pdf)
        self.assertIsInstance(result, Checklist)

    def test_invalid_output_errors_omit_model_input_and_exception_context(self):
        invalid = fixture()
        invalid["steps"][0]["expected_counts"]["yellow plate"] = "private-model-content"
        with patch.object(meta_client, "compile_manual", return_value=invalid):
            with self.assertRaises(InvalidChecklistError) as raised:
                compile_checklist(manual_pdf())
        self.assertNotIn("private-model-content", json.dumps(raised.exception.errors))
        self.assertTrue(raised.exception.errors)


class CompilerEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store_patch = patch.object(main.app.state, "session_store", SessionStore(Path(self.directory.name)))
        self.store_patch.start()
        self.addCleanup(self.store_patch.stop)
        self.mode = patch.object(meta_client, "MOCK_MODE", True)
        self.mode.start()
        self.addCleanup(self.mode.stop)
        self.client = AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()

    async def upload(self, content=None, mime="application/pdf"):
        return await self.client.post(
            "/compile-manual",
            files={"file": ("manual.pdf", manual_pdf() if content is None else content, mime)},
        )

    async def test_pdf_upload_returns_validated_mock_checklist(self):
        with patch.object(main, "MOCK_MODE", True):
            response = await self.upload()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), fixture())
        self.assertEqual(response.headers["x-stepguard-mode"], "MOCK")
        self.assertEqual(response.headers["cache-control"], "no-store")
        session = main.app.state.session_store.get(response.headers["x-stepguard-session-id"])
        self.assertEqual([step.status for step in session.steps], ["ACTIVE", "LOCKED"])

    async def test_invalid_uploads_never_reach_the_compiler(self):
        cases = [(b"", "application/pdf", 400), (b"not a PDF", "application/pdf", 400),
                 (manual_pdf(), "text/plain", 415)]
        with patch("backend.compiler.meta_client.compile_manual") as compiler:
            for content, mime, status in cases:
                with self.subTest(status=status, mime=mime, content=content[:20]):
                    response = await self.upload(content, mime)
                    self.assertEqual(response.status_code, status)
            compiler.assert_not_called()

    async def test_oversized_upload_is_rejected(self):
        content = b"%PDF-1.4\n" + b" " * main.MAX_MANUAL_BYTES
        with patch.object(meta_client, "compile_manual") as compiler:
            response = await self.upload(content)
        self.assertEqual(response.status_code, 413)
        compiler.assert_not_called()

    async def test_missing_upload_is_rejected(self):
        response = await self.client.post("/compile-manual")
        self.assertEqual(response.status_code, 422)

    async def test_invalid_compiler_output_returns_a_clear_502(self):
        invalid = deepcopy(fixture())
        invalid["steps"][0]["zone_anchor"] = "not a SAM prompt"
        with patch.object(meta_client, "compile_manual", return_value=invalid):
            response = await self.upload()
        self.assertEqual(response.status_code, 502)
        self.assertIn("invalid checklist", response.json()["detail"]["message"])
        self.assertTrue(response.json()["detail"]["errors"])

    async def test_real_mode_returns_503_without_loading_a_fixture(self):
        with patch.object(meta_client, "MOCK_MODE", False), patch.object(meta_client, "_fixture") as load_fixture:
            response = await self.upload()
        self.assertEqual(response.status_code, 503)
        load_fixture.assert_not_called()

    async def test_health_reports_current_milestone_and_openapi_describes_compiler(self):
        response = await self.client.get("/health")
        self.assertEqual(response.json()["milestone"], "M6")
        spec = (await self.client.get("/openapi.json")).json()
        operation = spec["paths"]["/compile-manual"]["post"]
        self.assertIn("multipart/form-data", operation["requestBody"]["content"])
        schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
        self.assertEqual(schema["$ref"], "#/components/schemas/Checklist")


if __name__ == "__main__":
    unittest.main()
