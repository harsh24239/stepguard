"""Exercise the M7 harness with original pixels and injected internal responses.

These are tests of reporting/validation, not evidence of real SAM performance.
"""

import base64
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image

from backend import meta_client
from scripts.day1_sam_test import MAX_IMAGE_BYTES, SAMCheckUnavailable, evaluate, main

PHRASES = ["yellow plate", "black pin", "silver screw", "red beam", "black wheel"]


def png(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def detection(phrase, **changes):
    return {"label": phrase, "box": [10, 10, 30, 30], "score": .9, "mask_png_base64": "", **changes}


class SAMCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image_bytes = png(Image.new("RGB", (640, 480), "#13202a"))

    def run_live(self, found=4, **kwargs):
        def segment(image, phrase):
            self.assertEqual(image, self.image_bytes)
            return [detection(phrase)] if phrase in PHRASES[:found] else []
        with patch.object(meta_client, "MOCK_MODE", False), patch.object(meta_client, "segment", side_effect=segment) as adapter:
            report = evaluate(self.image_bytes, PHRASES, **kwargs)
        self.assertEqual([call.args[1] for call in adapter.call_args_list], PHRASES)
        return report

    def test_four_of_five_reliable_phrases_meet_the_real_gate(self):
        report = self.run_live()
        self.assertEqual(report["decision"], "go")
        self.assertEqual(report["found_phrases"], 4)
        self.assertEqual(report["image_size"], [640, 480])
        self.assertEqual(report["results"][0]["scores"], [.9])
        self.assertFalse(report["results"][-1]["found"])
        self.assertEqual(report["results"][0]["mask_count"], 0)

    def test_fewer_than_four_is_no_go_in_real_mode(self):
        self.assertEqual(self.run_live(found=3)["decision"], "no_go")

    def test_mock_requires_explicit_opt_in_and_never_reports_go(self):
        with patch.object(meta_client, "MOCK_MODE", True), patch.object(meta_client, "segment") as adapter:
            with self.assertRaisesRegex(ValueError, "MOCK_MODE=false"):
                evaluate(self.image_bytes, PHRASES)
            adapter.assert_not_called()
        with patch.object(meta_client, "MOCK_MODE", True), patch.object(meta_client, "segment", side_effect=lambda _, phrase: [detection(phrase)]):
            report = evaluate(self.image_bytes, PHRASES, allow_mock=True)
        self.assertEqual(report["found_phrases"], 5)
        self.assertEqual(report["mode"], "MOCK")
        self.assertEqual(report["decision"], "not_evaluated_mock")

    def test_normal_mock_boundary_is_usable_but_not_sam_evidence(self):
        with patch.object(meta_client, "MOCK_MODE", True):
            report = evaluate(self.image_bytes, PHRASES, allow_mock=True)
        self.assertEqual(report["found_phrases"], 2)
        self.assertEqual(report["results"][1]["detection_count"], 4)
        self.assertEqual(report["decision"], "not_evaluated_mock")

    def test_five_distinct_nonblank_phrases_are_required_before_calls(self):
        with patch.object(meta_client, "segment") as adapter:
            for phrases in [PHRASES[:4], PHRASES + ["extra"], PHRASES[:4] + [" "], PHRASES[:4] + [" YELLOW PLATE "]]:
                with self.subTest(phrases=phrases), self.assertRaises(ValueError):
                    evaluate(self.image_bytes, phrases, allow_mock=True)
            adapter.assert_not_called()

    def test_invalid_or_oversized_image_is_rejected_before_calls(self):
        with patch.object(meta_client, "segment") as adapter:
            for image in [b"", b"not an image", b"x" * (MAX_IMAGE_BYTES + 1)]:
                with self.assertRaises(ValueError):
                    evaluate(image, PHRASES, allow_mock=True)
            adapter.assert_not_called()

    def test_low_score_and_tiny_detections_do_not_count_as_found(self):
        with patch.object(meta_client, "MOCK_MODE", False), patch.object(meta_client, "segment", side_effect=lambda _, phrase: [
            detection(phrase, score=.69), detection(phrase, box=[10, 10, 11, 11]),
        ]):
            report = evaluate(self.image_bytes, PHRASES)
        self.assertEqual(report["found_phrases"], 0)
        self.assertEqual(report["results"][0]["detection_count"], 2)
        self.assertEqual(report["results"][0]["scores"], [.69, .9])

    def test_valid_full_frame_masks_are_counted_and_payloads_omitted(self):
        mask = Image.new("L", (640, 480), 0)
        mask.paste(255, (10, 10, 30, 30))
        encoded = base64.b64encode(png(mask)).decode()
        with patch.object(meta_client, "MOCK_MODE", False), patch.object(meta_client, "segment", side_effect=lambda _, phrase: [detection(phrase, mask_png_base64=encoded)]):
            report = evaluate(self.image_bytes, PHRASES)
        self.assertEqual(report["results"][0]["mask_count"], 1)
        self.assertNotIn(encoded, json.dumps(report))
        self.assertNotIn("image_base64", json.dumps(report))

    def test_invalid_internal_output_is_an_error_not_no_go(self):
        for response in [{"private": "RAW_PRIVATE"}, [detection(PHRASES[0], score=float("nan"))],
                         [detection("wrong label")], [detection(PHRASES[0], box=[0, 0, 1000, 1000])],
                         [detection(PHRASES[0], mask_png_base64="RAW_PRIVATE")]]:
            with patch.object(meta_client, "MOCK_MODE", False), patch.object(meta_client, "segment", return_value=response):
                with self.assertRaises(SAMCheckUnavailable) as raised:
                    evaluate(self.image_bytes, PHRASES)
                self.assertNotIn("RAW_PRIVATE", str(raised.exception))

    def test_unavailable_and_failed_adapter_do_not_become_part_failures(self):
        for error in [NotImplementedError("PRIVATE_KEY"), RuntimeError("PRIVATE_KEY")]:
            with patch.object(meta_client, "MOCK_MODE", False), patch.object(meta_client, "segment", side_effect=error):
                with self.assertRaises(SAMCheckUnavailable) as raised:
                    evaluate(self.image_bytes, PHRASES)
                self.assertNotIn("PRIVATE_KEY", str(raised.exception))

    def test_real_boundary_still_refuses_to_load_fixtures(self):
        with patch.object(meta_client, "MOCK_MODE", False), patch.object(meta_client, "_fixture") as fixture:
            with self.assertRaises(SAMCheckUnavailable):
                evaluate(self.image_bytes, PHRASES)
        fixture.assert_not_called()

    def test_cli_saves_labeled_mock_summary_without_touching_input(self):
        with TemporaryDirectory() as directory:
            image, output = Path(directory) / "image.png", Path(directory) / "report.json"
            image.write_bytes(self.image_bytes)
            args = ["--image", str(image), "--report", str(output), "--allow-mock"]
            args += [item for phrase in PHRASES for item in ("--phrase", phrase)]
            with patch.object(meta_client, "MOCK_MODE", True), redirect_stdout(io.StringIO()) as stdout:
                code = main(args)
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(stdout.getvalue()), json.loads(output.read_text()))
            self.assertEqual(image.read_bytes(), self.image_bytes)
            self.assertEqual(json.loads(output.read_text())["decision"], "not_evaluated_mock")

    def test_cli_distinguishes_go_no_go_and_adapter_errors(self):
        with TemporaryDirectory() as directory:
            image = Path(directory) / "image.png"
            image.write_bytes(self.image_bytes)
            args = ["--image", str(image)] + [item for phrase in PHRASES for item in ("--phrase", phrase)]
            with patch.object(meta_client, "MOCK_MODE", False):
                for count, expected in [(5, 0), (3, 1)]:
                    with patch.object(meta_client, "segment", side_effect=lambda _, phrase: [detection(phrase)] if phrase in PHRASES[:count] else []), redirect_stdout(io.StringIO()):
                        self.assertEqual(main(args), expected)
                with patch.object(meta_client, "segment", side_effect=RuntimeError("PRIVATE_KEY")), redirect_stdout(io.StringIO()) as stdout, redirect_stderr(io.StringIO()) as stderr:
                    self.assertEqual(main(args), 2)
                self.assertEqual(stdout.getvalue(), "")
                self.assertNotIn("PRIVATE_KEY", stderr.getvalue())

    def test_report_cannot_overwrite_source_or_its_symlink(self):
        with TemporaryDirectory() as directory:
            image, link = Path(directory) / "image.png", Path(directory) / "link.png"
            image.write_bytes(self.image_bytes)
            link.symlink_to(image)
            for output in [image, link]:
                args = ["--image", str(image), "--report", str(output), "--allow-mock"] + [item for phrase in PHRASES for item in ("--phrase", phrase)]
                with patch.object(meta_client, "MOCK_MODE", True), redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                    self.assertEqual(main(args), 2)
                self.assertEqual(image.read_bytes(), self.image_bytes)


if __name__ == "__main__":
    unittest.main()
