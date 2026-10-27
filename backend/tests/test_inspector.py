"""Geometry tests use project-authored fixture boxes and generated PNG masks."""

import base64
import io
import json
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from backend import meta_client
from backend.inspector import (
    Detection, InspectorConfig, InvalidImageError, box_iou, inspect_step, relation_holds,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def detection(label, box, score=0.95, foreground=None):
    item = {"label": label, "box": list(box), "score": score, "mask_png_base64": ""}
    if foreground is not None:
        item["mask_png_base64"] = base64.b64encode(png(Image.fromarray(foreground.astype("uint8") * 255))).decode()
    return item


def part(box):
    x1, y1, x2, y2 = box
    return Detection("part", box, .95, ((x1 + x2) / 2, (y1 + y2) / 2), (x2 - x1) * (y2 - y1))


class GeometryTests(unittest.TestCase):
    def test_iou_for_disjoint_identical_and_overlapping_boxes(self):
        self.assertEqual(box_iou((0, 0, 10, 10), (20, 20, 30, 30)), 0)
        self.assertEqual(box_iou((0, 0, 10, 10), (0, 0, 10, 10)), 1)
        self.assertAlmostEqual(box_iou((0, 0, 10, 10), (5, 0, 15, 10)), 1 / 3)

    def test_full_containment_and_disjoint_outside(self):
        anchor = part((10, 10, 90, 90))
        self.assertTrue(relation_holds("inside", part((10, 10, 90, 90)), anchor))
        self.assertFalse(relation_holds("inside", part((0, 20, 30, 30)), anchor))
        self.assertTrue(relation_holds("outside", part((0, 0, 10, 10)), anchor))
        self.assertFalse(relation_holds("outside", part((5, 5, 15, 15)), anchor))

    def test_directions_use_strict_centroid_comparison(self):
        anchor = part((40, 40, 60, 60))
        self.assertTrue(relation_holds("left_of", part((0, 45, 20, 55)), anchor))
        self.assertFalse(relation_holds("left_of", part((45, 0, 55, 20)), anchor))
        self.assertTrue(relation_holds("above", part((45, 0, 55, 20)), anchor))
        self.assertFalse(relation_holds("above", part((0, 45, 20, 55)), anchor))

    def test_all_quadrants_and_centerline(self):
        anchor = part((0, 0, 100, 100))
        boxes = {"top_left": (10, 10, 20, 20), "top_right": (70, 10, 80, 20),
                 "bottom_left": (10, 70, 20, 80), "bottom_right": (70, 70, 80, 80)}
        for relation, box in boxes.items():
            with self.subTest(relation=relation):
                self.assertTrue(relation_holds(relation, part(box), anchor))
                self.assertFalse(relation_holds(relation, part((45, 45, 55, 55)), anchor))
                self.assertFalse(relation_holds(relation, part((110, 110, 120, 120)), anchor))

    def test_invalid_thresholds_are_rejected(self):
        for values in ({"min_score": 2}, {"min_area_pixels": 0}, {"max_image_pixels": 0},
                       {"duplicate_iou": .4, "ambiguous_iou": .5}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                InspectorConfig(**values)


class InspectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image_bytes = png(Image.new("RGB", (640, 480), "#131b23"))

    def setUp(self):
        self.step = json.loads((FIXTURES / "checklist.json").read_text())["steps"][1]
        self.segments = json.loads((FIXTURES / "segments.json").read_text())

    def inspect(self, **kwargs):
        with patch.object(meta_client, "segment", side_effect=lambda image, prompt: deepcopy(self.segments.get(prompt, []))) as segment:
            result = inspect_step(self.step, self.image_bytes, **kwargs)
            calls = [call.args[1] for call in segment.call_args_list]
        return result, calls

    def test_fixture_scene_counts_four_pins_and_calls_anchor_first_once(self):
        result, calls = self.inspect()
        self.assertEqual(calls, ["yellow plate", "black pin"])
        self.assertEqual(result.found_counts, {"yellow plate": 1, "black pin": 4})
        self.assertTrue(result.counts_match)
        self.assertTrue(result.rules_hold)
        self.assertTrue(result.deterministic_checks_pass)
        self.assertEqual(result.issues, [])
        self.assertEqual(Image.open(io.BytesIO(result.annotated_image)).size, (640, 480))
        json.dumps(result.summary())

    def test_actual_mock_boundary_is_usable_without_patch_of_segment(self):
        with patch.object(meta_client, "MOCK_MODE", True):
            result = inspect_step(self.step, self.image_bytes)
        self.assertTrue(result.deterministic_checks_pass)

    def test_missing_anchor_stops_before_part_calls_and_leaves_counts_unknown(self):
        self.segments["yellow plate"] = []
        result, calls = self.inspect()
        self.assertEqual(calls, ["yellow plate"])
        self.assertEqual(result.found_counts, {})
        self.assertIsNone(result.counts_match)
        self.assertTrue(result.uncertain)
        self.assertEqual(result.issues[-1]["message"], "Can't see the assembly area. Check camera and lighting.")

    def test_multiple_anchors_stop_without_guessing_an_assembly_zone(self):
        self.segments["yellow plate"].append(detection("yellow plate", (5, 5, 60, 60)))
        result, calls = self.inspect()
        self.assertTrue(result.uncertain)
        self.assertEqual(calls, ["yellow plate"])

    def test_low_score_anchor_is_uncertain_and_stops(self):
        self.segments["yellow plate"][0]["score"] = .2
        result, calls = self.inspect()
        self.assertTrue(result.uncertain)
        self.assertEqual(calls, ["yellow plate"])

    def test_background_parts_are_zone_gated_before_scoring(self):
        self.segments["black pin"].append(detection("black pin", (5, 5, 25, 25), .1))
        result, _ = self.inspect()
        self.assertTrue(result.deterministic_checks_pass)
        self.assertEqual(result.filtering["black pin"]["outside_zone"], 1)

    def test_high_iou_duplicates_are_removed_and_best_score_is_kept(self):
        self.segments["black pin"].append(detection("black pin", (120, 100, 140, 120), .1))
        result, _ = self.inspect()
        self.assertTrue(result.deterministic_checks_pass)
        self.assertEqual(result.filtering["black pin"]["duplicate"], 1)
        self.assertTrue(all(item.score >= .7 for item in result.detections))

    def test_tiny_noise_is_removed(self):
        self.segments["black pin"].append(detection("black pin", (200, 200, 202, 202)))
        result, _ = self.inspect()
        self.assertTrue(result.deterministic_checks_pass)
        self.assertEqual(result.filtering["black pin"]["tiny"], 1)

    def test_missing_pin_fails_count_without_inventing_a_corner(self):
        self.segments["black pin"].pop()
        result, _ = self.inspect()
        self.assertFalse(result.counts_match)
        self.assertFalse(result.deterministic_checks_pass)
        self.assertFalse(result.uncertain)
        self.assertEqual(result.issues[0]["type"], "missing")
        self.assertEqual(result.issues[0]["location_hint"], "assembly area")

    def test_extra_pin_fails_count_and_is_included_in_evidence(self):
        self.segments["black pin"].append(detection("black pin", (200, 200, 220, 220)))
        result, _ = self.inspect()
        self.assertEqual(result.found_counts["black pin"], 5)
        self.assertFalse(result.counts_match)
        self.assertIn("expected 4", result.issues[0]["message"])

    def test_part_crossing_anchor_edge_is_gated_in_but_fails_inside_rule(self):
        self.segments["black pin"][0] = detection("black pin", (70, 100, 110, 120))
        result, _ = self.inspect()
        self.assertTrue(result.counts_match)
        self.assertFalse(result.rules_hold)
        self.assertIn("misplaced", [issue["type"] for issue in result.issues])

    def test_outside_rule_retains_parts_outside_anchor_and_flags_inside_parts(self):
        self.step["expected_counts"]["black pin"] = 1
        self.step["spatial_rules"][0]["relation"] = "outside"
        self.segments["black pin"] = [detection("black pin", (5, 5, 25, 25))]
        result, _ = self.inspect()
        self.assertTrue(result.deterministic_checks_pass)
        self.segments["black pin"] = [detection("black pin", (120, 100, 140, 120))]
        result, _ = self.inspect()
        self.assertFalse(result.rules_hold)

    def test_quadrant_rule_applies_to_every_instance(self):
        self.step["spatial_rules"][0]["relation"] = "top_right"
        result, _ = self.inspect()
        self.assertEqual(sum(result.rule_checks[0]["instance_matches"]), 1)
        self.assertEqual(len(result.rule_checks[0]["instance_matches"]), 4)
        self.assertFalse(result.rules_hold)

    def test_low_score_pin_cannot_yield_a_deterministic_pass(self):
        self.segments["black pin"][0]["score"] = .4
        result, _ = self.inspect()
        self.assertTrue(result.counts_match)
        self.assertTrue(result.uncertain)
        self.assertFalse(result.deterministic_checks_pass)

    def test_ambiguous_overlaps_block_pass_even_if_counts_are_adjusted_to_match(self):
        self.segments["black pin"].append(detection("black pin", (125, 100, 145, 120)))
        self.step["expected_counts"]["black pin"] = 5
        result, _ = self.inspect()
        self.assertTrue(result.counts_match)
        self.assertTrue(result.uncertain)
        self.assertFalse(result.deterministic_checks_pass)

    def test_conflicting_labels_block_pass(self):
        self.step["sam_prompts"].append("silver screw")
        self.step["expected_counts"]["silver screw"] = 1
        self.segments["silver screw"] = [detection("silver screw", (120, 100, 140, 120))]
        result, _ = self.inspect()
        self.assertTrue(result.counts_match)
        self.assertTrue(result.uncertain)

    def test_invalid_boxes_scores_and_masks_produce_uncertainty(self):
        original = self.segments["black pin"][0]
        variants = [{"box": [0, 0, float("nan"), 10]}, {"box": [-1, 0, 10, 10]},
                    {"box": [10, 0, 1, 10]}, {"box": [0, 0, 1000, 10]}, {"score": True},
                    {"score": 1.1}, {"mask_png_base64": "bad base64"}, {"label": "wheel"}]
        for values in variants:
            with self.subTest(values=values):
                self.segments["black pin"][0] = {**original, **values}
                result, _ = self.inspect()
                self.assertTrue(result.uncertain)
                self.assertFalse(result.deterministic_checks_pass)

    def test_invalid_image_never_reaches_segmentation(self):
        with patch.object(meta_client, "segment") as segment:
            with self.assertRaises(InvalidImageError):
                inspect_step(self.step, b"not an image")
            with self.assertRaises(InvalidImageError):
                inspect_step(self.step, self.image_bytes, InspectorConfig(max_image_pixels=100))
            segment.assert_not_called()

    def test_full_frame_png_mask_drives_area_centroid_and_bounds(self):
        foreground = np.zeros((480, 640), dtype=bool)
        foreground[100:120, 120:140] = True
        self.segments["black pin"][0] = detection("black pin", (0, 0, 640, 480), foreground=foreground)
        result, _ = self.inspect()
        item = next(item for item in result.detections if item.mask_png_base64)
        self.assertEqual(item.area, 400)
        self.assertEqual(item.centroid, (129.5, 109.5))
        self.assertEqual(item.box, (120, 100, 140, 120))
        self.assertTrue(result.deterministic_checks_pass)

    def test_sparse_mask_is_filtered_by_foreground_area_rather_than_box_area(self):
        foreground = np.zeros((480, 640), dtype=bool)
        foreground[200, 200] = True
        self.segments["black pin"].append(detection("black pin", (100, 100, 300, 300), foreground=foreground))
        result, _ = self.inspect()
        self.assertTrue(result.deterministic_checks_pass)
        self.assertEqual(result.filtering["black pin"]["tiny"], 1)

    def test_disjoint_masks_with_identical_bounds_are_not_merged(self):
        first = np.zeros((480, 640), dtype=bool)
        first[100:120:2, 120:140:2] = True
        first[119, 139] = True
        second = np.zeros_like(first)
        second[101:120:2, 121:140:2] = True
        second[100, 139] = second[119, 120] = True
        self.segments["black pin"][:1] = [
            detection("black pin", (120, 100, 140, 120), foreground=first),
            detection("black pin", (120, 100, 140, 120), foreground=second),
        ]
        self.step["expected_counts"]["black pin"] = 5
        result, _ = self.inspect()
        self.assertEqual(result.found_counts["black pin"], 5)
        self.assertEqual(result.filtering["black pin"]["duplicate"], 0)

    def test_duplicate_png_masks_are_merged(self):
        foreground = np.zeros((480, 640), dtype=bool)
        foreground[100:120, 120:140] = True
        item = detection("black pin", (120, 100, 140, 120), foreground=foreground)
        self.segments["black pin"][:1] = [item, deepcopy(item)]
        result, _ = self.inspect()
        self.assertTrue(result.deterministic_checks_pass)
        self.assertEqual(result.filtering["black pin"]["duplicate"], 1)

    def test_empty_and_wrong_sized_masks_are_uncertain(self):
        for foreground in (np.zeros((480, 640), dtype=bool), np.ones((10, 10), dtype=bool)):
            with self.subTest(shape=foreground.shape):
                self.segments["black pin"][0] = detection("black pin", (120, 100, 140, 120), foreground=foreground)
                result, _ = self.inspect()
                self.assertTrue(result.uncertain)

    def test_directional_rule_can_match_any_of_multiple_target_instances(self):
        self.step["sam_prompts"].append("red beam")
        self.step["expected_counts"]["red beam"] = 2
        self.step["spatial_rules"] = [{"part": "black pin", "relation": "left_of", "target": "red beam"}]
        self.segments["red beam"] = [detection("red beam", (90, 200, 100, 220)),
                                      detection("red beam", (540, 200, 550, 220))]
        result, _ = self.inspect()
        self.assertTrue(result.deterministic_checks_pass)

    def test_outside_a_non_anchor_target_does_not_disable_assembly_zone_gating(self):
        self.step["sam_prompts"].append("red beam")
        self.step["expected_counts"]["red beam"] = 1
        self.step["spatial_rules"] = [{"part": "black pin", "relation": "outside", "target": "red beam"}]
        self.segments["red beam"] = [detection("red beam", (300, 200, 320, 220))]
        self.segments["black pin"].append(detection("black pin", (5, 5, 25, 25)))
        result, _ = self.inspect()
        self.assertTrue(result.deterministic_checks_pass)
        self.assertEqual(result.filtering["black pin"]["outside_zone"], 1)

    def test_absent_non_anchor_target_cannot_satisfy_a_spatial_rule(self):
        self.step["sam_prompts"].append("red beam")
        self.step["expected_counts"]["red beam"] = 1
        self.step["spatial_rules"] = [{"part": "black pin", "relation": "left_of", "target": "red beam"}]
        result, _ = self.inspect()
        self.assertFalse(result.rules_hold)
        self.assertFalse(result.counts_match)
        self.assertFalse(any(issue["type"] == "misplaced" for issue in result.issues))

    def test_expected_zero_parts_do_not_fail_a_vacuous_inside_rule(self):
        self.step["expected_counts"]["black pin"] = 0
        self.segments["black pin"] = []
        result, _ = self.inspect()
        self.assertTrue(result.deterministic_checks_pass)

    def test_uncertainty_colors_boxes_amber_even_with_a_count_failure(self):
        self.segments["black pin"][0]["score"] = .4
        self.segments["black pin"].pop()
        result, _ = self.inspect()
        annotated = Image.open(io.BytesIO(result.annotated_image))
        self.assertTrue(result.uncertain)
        self.assertFalse(result.counts_match)
        self.assertEqual(annotated.getpixel((120, 100)), (244, 189, 98))

    def test_real_mode_does_not_fall_back_to_fixture_segmentation(self):
        with patch.object(meta_client, "MOCK_MODE", False), patch.object(meta_client, "_fixture") as fixture:
            with self.assertRaises(NotImplementedError):
                inspect_step(self.step, self.image_bytes)
            fixture.assert_not_called()

    def test_invalid_segmentation_list_is_uncertain_instead_of_missing_parts(self):
        self.segments["black pin"] = {"unexpected": "response"}
        result, _ = self.inspect()
        self.assertTrue(result.uncertain)
        self.assertFalse(result.deterministic_checks_pass)

    def test_alpha_mask_uses_foreground_alpha_instead_of_background_rgb(self):
        image = Image.new("RGBA", (640, 480), (255, 255, 255, 0))
        image.paste((0, 0, 0, 255), (120, 100, 140, 120))
        self.segments["black pin"][0]["mask_png_base64"] = base64.b64encode(png(image)).decode()
        result, _ = self.inspect()
        item = next(item for item in result.detections if item.mask_png_base64)
        self.assertEqual(item.area, 400)
        self.assertTrue(result.deterministic_checks_pass)


if __name__ == "__main__":
    unittest.main()
