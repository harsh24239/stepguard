"""Verdict guards exercise real deterministic evidence and injected model outputs."""

import io
import json
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from backend import meta_client
from backend.inspector import inspect_step
from backend.judge import judge_step
from backend.schemas import ChecklistStep

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def model_output(verdict="pass", confidence=.99, issues=None):
    return {"verdict": verdict, "confidence": confidence, "issues": issues or [], "fix_hint": "Check the assembly."}


class JudgeTests(unittest.TestCase):
    def setUp(self):
        self.step = ChecklistStep.model_validate(json.loads((FIXTURES / "checklist.json").read_text())["steps"][1])
        self.segments = json.loads((FIXTURES / "segments.json").read_text())
        buffer = io.BytesIO()
        Image.new("RGB", (640, 480)).save(buffer, format="PNG")
        self.image = buffer.getvalue()

    def evidence(self):
        with patch.object(meta_client, "segment", side_effect=lambda image, prompt: deepcopy(self.segments[prompt])):
            return inspect_step(self.step, self.image)

    def result(self, output, evidence=None):
        evidence = self.evidence() if evidence is None else evidence
        with patch.object(meta_client, "judge", return_value=output):
            return judge_step(self.step, evidence)

    def test_pass_requires_matching_counts_geometry_and_no_issues(self):
        result = self.result(model_output())
        self.assertEqual(result.verdict, "pass")
        self.assertEqual(result.issues, [])
        self.assertEqual(result.message, "Step 2 passed.")
        self.assertFalse(result.next_step_unlocked)  # Only the state machine may unlock.

    def test_count_failure_cannot_be_overridden_by_a_model_pass(self):
        self.segments["black pin"].pop()
        result = self.result(model_output())
        self.assertEqual(result.verdict, "fail")
        self.assertEqual(result.message, "Step 2 is wrong: 1 black pin missing, assembly area.")
        self.assertEqual(result.fix_hint, "Add 1 black pin to the assembly area.")

    def test_geometry_failure_cannot_be_overridden_by_a_model_pass(self):
        self.segments["black pin"][0]["box"] = [70, 100, 110, 120]
        result = self.result(model_output())
        self.assertEqual(result.verdict, "fail")
        self.assertIn("Move it inside yellow plate", result.message)
        self.assertTrue(any(mask.status == "bad" for mask in result.masks))

    def test_extra_parts_have_a_removal_hint(self):
        self.segments["black pin"].append({**self.segments["black pin"][0], "box": [200, 200, 220, 220]})
        result = self.result(model_output())
        self.assertEqual(result.verdict, "fail")
        self.assertEqual(result.fix_hint, "Remove 1 extra black pin from the assembly area.")

    def test_model_can_downgrade_a_count_failure_to_unsure(self):
        self.segments["black pin"].pop()
        result = self.result(model_output("unsure"))
        self.assertEqual(result.verdict, "unsure")
        self.assertEqual(result.message, "Please check Step 2 (low confidence).")

    def test_low_detection_score_skips_model_and_stays_unsure(self):
        self.segments["black pin"][0]["score"] = .2
        evidence = self.evidence()
        with patch.object(meta_client, "judge") as judge:
            result = judge_step(self.step, evidence)
        judge.assert_not_called()
        self.assertEqual(result.verdict, "unsure")
        self.assertTrue(all(mask.status == "ok" for mask in result.masks))

    def test_missing_anchor_skips_judge_and_gives_camera_hint(self):
        self.segments["yellow plate"] = []
        evidence = self.evidence()
        with patch.object(meta_client, "judge") as judge:
            result = judge_step(self.step, evidence)
        judge.assert_not_called()
        self.assertEqual(result.verdict, "unsure")
        self.assertIn("Can't see the assembly area", result.fix_hint)
        self.assertEqual(result.found_counts, {})

    def test_low_judge_confidence_stays_unsure_even_for_a_model_pass(self):
        result = self.result(model_output(confidence=.2))
        self.assertEqual(result.verdict, "unsure")
        self.assertTrue(any(issue.type == "low_confidence" for issue in result.issues))

    def test_low_confidence_issue_takes_precedence_over_high_confidence_fail(self):
        issue = {"type": "low_confidence", "part": "pin", "location_hint": "assembly area", "message": "Occluded."}
        result = self.result(model_output("fail", issues=[issue]))
        self.assertEqual(result.verdict, "unsure")

    def test_pass_with_an_issue_cannot_pass_and_uses_wrong_part_feedback(self):
        issue = {"type": "wrong_part", "part": "black pin", "location_hint": "top-right",
                 "message": "A red pin is where a black pin should be. Swap them."}
        result = self.result(model_output(issues=[issue]))
        self.assertEqual(result.verdict, "fail")
        self.assertIn("Swap them", result.message)

    def test_unexplained_model_failure_becomes_unsure(self):
        self.assertEqual(self.result(model_output("fail")).verdict, "unsure")

    def test_invalid_model_outputs_never_pass_or_echo_the_raw_payload(self):
        variants = [{}, {**model_output(), "confidence": float("nan")},
                    {**model_output(), "confidence": 2}, {**model_output(), "extra": "private-content"},
                    {**model_output(), "verdict": "private-content"},
                    {**model_output(), "issues": [{"message": "private-content"}]}]
        for output in variants:
            with self.subTest(output=output):
                result = self.result(output)
                self.assertEqual(result.verdict, "unsure")
                self.assertNotIn("private-content", result.model_dump_json())

    def test_confidence_is_capped_by_the_weakest_detection(self):
        self.assertAlmostEqual(self.result(model_output()).confidence, .94)

    def test_model_receives_compact_evidence_and_the_annotated_image(self):
        evidence = self.evidence()
        with patch.object(meta_client, "judge", return_value=model_output()) as judge:
            judge_step(self.step, evidence)
        step, found, geometry, image = judge.call_args.args
        self.assertEqual(step["step_id"], 2)
        self.assertEqual(found["found_counts"]["black pin"], 4)
        self.assertTrue(geometry["counts_match"])
        self.assertTrue(image.startswith(b"\x89PNG"))
        self.assertNotIn("mask_png_base64", json.dumps(geometry))

    def test_default_mock_judge_remains_unsure(self):
        with patch.object(meta_client, "MOCK_MODE", True):
            result = judge_step(self.step, self.evidence())
        self.assertEqual(result.verdict, "unsure")
        self.assertIn("mock", result.fix_hint.lower())

    def test_evidence_from_a_different_step_is_rejected(self):
        evidence = self.evidence()
        evidence.step_id = 1
        with self.assertRaises(ValueError):
            judge_step(self.step, evidence)

    def test_counts_are_compared_directly_even_if_evidence_flags_are_inconsistent(self):
        evidence = self.evidence()
        evidence.found_counts["black pin"] = 3
        self.assertNotEqual(self.result(model_output(), evidence).verdict, "pass")
