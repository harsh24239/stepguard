"""Anchor-first segmentation and deterministic geometry; no judge or step state.

Internal coordinates are full-image pixels: [left, top, right, bottom]. An
optional mask is a full-frame PNG (grayscale foreground, or nonopaque alpha).
The real SAM adapter must normalize its verified response into this contract.
"""

import base64
import binascii
import io
import math
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageDraw, UnidentifiedImageError

from backend import meta_client
from backend.schemas import ChecklistStep, Relation

Box = tuple[float, float, float, float]


@dataclass(frozen=True)
class InspectorConfig:
    min_area_pixels: int = 16
    min_score: float = 0.7
    duplicate_iou: float = 0.85
    ambiguous_iou: float = 0.5
    max_image_pixels: int = 12_000_000

    def __post_init__(self):
        if self.min_area_pixels < 1 or self.max_image_pixels < 1:
            raise ValueError("Image and area limits must be positive")
        if not 0 <= self.min_score <= 1:
            raise ValueError("min_score must be between zero and one")
        if not 0 < self.ambiguous_iou < self.duplicate_iou <= 1:
            raise ValueError("IoU thresholds must satisfy 0 < ambiguous < duplicate <= 1")


@dataclass(frozen=True)
class Detection:
    label: str
    box: Box
    score: float
    centroid: tuple[float, float]
    area: int | float
    mask_png_base64: str = ""
    _foreground: np.ndarray | None = field(default=None, repr=False, compare=False)


@dataclass
class InspectionResult:
    step_id: int
    expected_counts: dict[str, int]
    found_counts: dict[str, int] = field(default_factory=dict)
    counts_match: bool | None = None
    rules_hold: bool | None = None
    uncertain: bool = False
    issues: list[dict] = field(default_factory=list)
    count_checks: list[dict] = field(default_factory=list)
    rule_checks: list[dict] = field(default_factory=list)
    filtering: dict[str, dict[str, int]] = field(default_factory=dict)
    detections: list[Detection] = field(default_factory=list)
    annotated_image: bytes = b""

    @property
    def deterministic_checks_pass(self) -> bool:
        return self.counts_match is True and self.rules_hold is True and not self.uncertain

    def summary(self) -> dict:
        """Compact evidence for the future judge; excludes image/mask payloads."""
        return {
            "step_id": self.step_id,
            "expected_counts": self.expected_counts,
            "found_counts": self.found_counts,
            "counts_match": self.counts_match,
            "rules_hold": self.rules_hold,
            "uncertain": self.uncertain,
            "deterministic_checks_pass": self.deterministic_checks_pass,
            "issues": self.issues,
            "count_checks": self.count_checks,
            "rule_checks": self.rule_checks,
            "filtering": self.filtering,
            "detections": [
                {"label": item.label, "box": item.box, "score": item.score,
                 "centroid": item.centroid, "area": item.area}
                for item in self.detections
            ],
        }


class InvalidImageError(ValueError):
    """Input bytes are not a supported, bounded image."""


def box_iou(first: Box, second: Box) -> float:
    intersection = max(0, min(first[2], second[2]) - max(first[0], second[0])) * max(
        0, min(first[3], second[3]) - max(first[1], second[1])
    )
    union = ((first[2] - first[0]) * (first[3] - first[1])
             + (second[2] - second[0]) * (second[3] - second[1]) - intersection)
    return intersection / union if union > 0 else 0.0


def _point_inside(point: tuple[float, float], box: Box) -> bool:
    # Half-open bounds match pixel boxes, Pillow crops, and mask bounding boxes.
    return box[0] <= point[0] < box[2] and box[1] <= point[1] < box[3]


def _overlap(first: Detection, second: Detection) -> float:
    if first._foreground is not None and second._foreground is not None:
        intersection = np.count_nonzero(first._foreground & second._foreground)
        union = np.count_nonzero(first._foreground | second._foreground)
        return float(intersection / union) if union else 0.0
    return box_iou(first.box, second.box)


def decode_image(image_bytes: bytes, config: InspectorConfig) -> Image.Image:
    """Decode a bounded RGB image for inspection or the standalone SAM check."""
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            if image.width * image.height > config.max_image_pixels:
                raise InvalidImageError("The image exceeds the inspector pixel limit.")
            return image.convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise InvalidImageError("Supply a decodable camera image.") from error


def normalize_detection(raw: dict, prompt: str, size: tuple[int, int]) -> Detection:
    """Validate the internal pixel-box/full-frame-mask contract from the adapter."""
    if not isinstance(raw, dict) or raw.get("label") != prompt:
        raise ValueError("Detection must match the requested label")
    box = raw.get("box")
    score = raw.get("score")
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        raise ValueError("Detection needs four box coordinates")
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in box):
        raise ValueError("Box coordinates must be finite numbers")
    if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1:
        raise ValueError("Detection score must be between zero and one")
    left, top, right, bottom = box
    if not (0 <= left < right <= size[0] and 0 <= top < bottom <= size[1]):
        raise ValueError("Detection box is outside the image or has no area")
    mask = raw.get("mask_png_base64", "")
    if not isinstance(mask, str):
        raise ValueError("Mask must be base64 PNG text")
    area = (right - left) * (bottom - top)
    centroid = ((left + right) / 2, (top + bottom) / 2)
    foreground = None
    if mask:
        try:
            with Image.open(io.BytesIO(base64.b64decode(mask, validate=True))) as image:
                if image.format != "PNG" or image.size != size:
                    raise ValueError("Mask must be a full-frame PNG")
                # Alpha cutouts and grayscale masks are both project-supported.
                if image.mode == "RGBA" and image.getextrema()[3] != (255, 255):
                    pixels = np.asarray(image.getchannel("A"))
                else:
                    pixels = np.asarray(image.convert("L"))
                foreground = pixels > 127
                ys, xs = np.nonzero(foreground)
                if not len(xs):
                    raise ValueError("Mask has no foreground")
                area = int(len(xs))
                centroid = (float(xs.mean()), float(ys.mean()))
                left, top, right, bottom = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
        except (binascii.Error, UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
            raise ValueError("Invalid mask PNG") from error
    return Detection(prompt, (left, top, right, bottom), float(score), centroid, area, mask, foreground)


def relation_holds(relation: Relation, part: Detection, target: Detection) -> bool:
    """inside=full box containment; outside=no box intersection; directions=centroids.

    Quadrants use the target bounding-box midpoint and require the part centroid
    inside that box. A centroid exactly on a dividing axis satisfies no quadrant.
    """
    a, b = part.box, target.box
    if relation == "inside":
        return b[0] <= a[0] and b[1] <= a[1] and a[2] <= b[2] and a[3] <= b[3]
    if relation == "outside":
        return a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]
    if relation == "left_of":
        return part.centroid[0] < target.centroid[0]
    if relation == "above":
        return part.centroid[1] < target.centroid[1]
    if relation not in {"top_left", "top_right", "bottom_left", "bottom_right"}:
        raise ValueError("Unsupported spatial relation")
    x, y = part.centroid
    mid_x, mid_y = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    return _point_inside(part.centroid, b) and (
        x < mid_x if relation.endswith("left") else x > mid_x
    ) and (y < mid_y if relation.startswith("top") else y > mid_y)


def _issue(result: InspectionResult, kind: str, part: str, message: str, location: str = "assembly area"):
    result.issues.append({"type": kind, "part": part, "location_hint": location, "message": message})
    if kind == "low_confidence":
        result.uncertain = True


def _candidates(image_bytes, prompt, size, result, config, zone=None) -> list[Detection]:
    raw_items = meta_client.segment(image_bytes, prompt)
    stats = result.filtering[prompt] = {"tiny": 0, "duplicate": 0, "outside_zone": 0, "invalid": 0}
    if not isinstance(raw_items, list):
        _issue(result, "low_confidence", prompt, "Segmentation returned an invalid detection list.")
        return []
    items = []
    for raw in raw_items:
        try:
            item = normalize_detection(raw, prompt, size)
        except ValueError:
            stats["invalid"] += 1
            _issue(result, "low_confidence", prompt, "A detection could not be validated; check the camera image.")
            continue
        if item.area < config.min_area_pixels:
            stats["tiny"] += 1
        elif zone is not None and not _point_inside(item.centroid, zone):
            stats["outside_zone"] += 1
        else:
            items.append(item)
    kept = []
    for item in sorted(items, key=lambda item: item.score, reverse=True):
        if any(_overlap(item, existing) >= config.duplicate_iou for existing in kept):
            stats["duplicate"] += 1
            continue
        if any(_overlap(item, existing) >= config.ambiguous_iou for existing in kept):
            _issue(result, "low_confidence", prompt, "Overlapping detections make the part count ambiguous.")
        if item.score < config.min_score:
            _issue(result, "low_confidence", prompt, "A part detection has a low score; check camera and lighting.")
        kept.append(item)
    return kept


def _annotate(image: Image.Image, result: InspectionResult, bad: set[int]) -> bytes:
    draw = ImageDraw.Draw(image)
    for index, item in enumerate(result.detections):
        color = "#f4bd62" if result.uncertain else "#f07878" if index in bad else "#7ce0ac"
        draw.rectangle(item.box, outline=color, width=3)
        draw.text((item.box[0] + 4, item.box[1] + 4), item.label.encode("ascii", "replace").decode(), fill=color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def inspect_step(
    step: ChecklistStep | dict, image_bytes: bytes, config: InspectorConfig | None = None,
) -> InspectionResult:
    """Produce evidence for M4. This function never calls the judge or unlocks a step."""
    step = ChecklistStep.model_validate(step) if isinstance(step, dict) else step
    config = config or InspectorConfig()
    image = decode_image(image_bytes, config)
    result = InspectionResult(step.step_id, dict(step.expected_counts))
    anchor_items = _candidates(image_bytes, step.zone_anchor, image.size, result, config)
    result.detections.extend(anchor_items)
    if len(anchor_items) != 1 or result.uncertain:
        message = ("Can't see the assembly area. Check camera and lighting." if not anchor_items
                   else "Can't identify one reliable assembly area. Check camera and lighting.")
        _issue(result, "low_confidence", step.zone_anchor, message)
        result.annotated_image = _annotate(image, result, set())
        return result

    anchor = anchor_items[0]
    by_prompt = {step.zone_anchor: anchor_items}
    for prompt in step.sam_prompts:
        if prompt == step.zone_anchor:
            continue
        allow_outside = any(rule.part == prompt and rule.relation == "outside"
                            and rule.target == step.zone_anchor for rule in step.spatial_rules)
        items = _candidates(image_bytes, prompt, image.size, result, config,
                            zone=None if allow_outside else anchor.box)
        by_prompt[prompt] = items
        result.detections.extend(items)

    # Conflicting labels for the same apparent object cannot yield a confident count.
    for index, item in enumerate(result.detections):
        for other in result.detections[index + 1:]:
            if item.label != other.label and _overlap(item, other) >= config.duplicate_iou:
                _issue(result, "low_confidence", item.label, "Overlapping part labels make identification ambiguous.")

    result.found_counts = {prompt: len(by_prompt[prompt]) for prompt in step.sam_prompts}
    bad = set()
    for prompt, expected in step.expected_counts.items():
        found = result.found_counts[prompt]
        result.count_checks.append({"part": prompt, "expected": expected, "found": found, "matches": found == expected})
        if found < expected:
            _issue(result, "missing", prompt, f"{expected - found} {prompt} missing from the assembly area.")
        elif found > expected:
            _issue(result, "wrong_part", prompt, f"Found {found} {prompt}; expected {expected}. Remove the extra parts.")
            bad.update(i for i, item in enumerate(result.detections) if item.label == prompt)
    result.counts_match = all(check["matches"] for check in result.count_checks)

    for rule in step.spatial_rules:
        sources, targets = by_prompt[rule.part], by_prompt[rule.target]
        matches = []
        for part in sources:
            holds = any(relation_holds(rule.relation, part, target) for target in targets)
            matches.append(holds)
            if not holds and targets:
                bad.add(result.detections.index(part))
                _issue(result, "misplaced", rule.part,
                       f"{rule.part} does not satisfy {rule.relation.replace('_', ' ')} relative to {rule.target}.")
        holds = all(matches) and (bool(sources) or step.expected_counts[rule.part] == 0)
        result.rule_checks.append({**rule.model_dump(), "holds": holds, "instance_matches": matches})
    result.rules_hold = all(check["holds"] for check in result.rule_checks)
    result.annotated_image = _annotate(image, result, bad)
    return result
