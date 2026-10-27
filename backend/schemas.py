"""Validated manual checklist contract shared by compilation and inspection."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

VisualPhrase = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Count = Annotated[int, Field(ge=0)]
Relation = Literal[
    "inside", "outside", "left_of", "above",
    "top_left", "top_right", "bottom_left", "bottom_right",
]


class ChecklistModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SpatialRule(ChecklistModel):
    part: VisualPhrase
    relation: Relation
    target: VisualPhrase


class ChecklistStep(ChecklistModel):
    step_id: Annotated[int, Field(ge=1)]
    instruction: VisualPhrase
    sam_prompts: Annotated[list[VisualPhrase], Field(min_length=1)]
    expected_counts: Annotated[dict[VisualPhrase, Count], Field(min_length=1)]
    zone_anchor: VisualPhrase
    spatial_rules: list[SpatialRule]
    fix_hint_template: VisualPhrase

    @model_validator(mode="after")
    def validate_part_references(self) -> Self:
        prompts = set(self.sam_prompts)
        if len(prompts) != len(self.sam_prompts):
            raise ValueError("sam_prompts must be unique")
        if self.zone_anchor not in prompts:
            raise ValueError("zone_anchor must reference a SAM prompt")
        if set(self.expected_counts) != prompts:
            raise ValueError("expected_counts must specify each SAM prompt exactly once")
        if self.expected_counts[self.zone_anchor] < 1:
            raise ValueError("zone_anchor must have a positive expected count")
        for rule in self.spatial_rules:
            if rule.part not in prompts or rule.target not in prompts:
                raise ValueError("spatial rules must reference SAM prompts in this step")
            if rule.part == rule.target:
                raise ValueError("a spatial rule must compare different parts")
        return self


class Checklist(ChecklistModel):
    product: VisualPhrase
    steps: Annotated[list[ChecklistStep], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_step_order(self) -> Self:
        if [step.step_id for step in self.steps] != list(range(1, len(self.steps) + 1)):
            raise ValueError("step IDs must be consecutive, ordered, and start at 1")
        return self


SessionId = Annotated[str, StringConstraints(
    pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)]
Verdict = Literal["pass", "fail", "unsure"]
StepStatus = Literal["LOCKED", "ACTIVE", "CHECKING", "PASSED", "FAILED", "UNSURE"]
Confidence = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class Issue(ChecklistModel):
    type: Literal["missing", "wrong_part", "misplaced", "low_confidence"]
    part: VisualPhrase
    location_hint: VisualPhrase
    message: VisualPhrase


class JudgeOutput(ChecklistModel):
    verdict: Verdict
    confidence: Confidence
    issues: list[Issue]
    fix_hint: VisualPhrase


class OverlayMask(ChecklistModel):
    label: str
    box: tuple[float, float, float, float]
    status: Literal["ok", "bad"]
    mask_png_base64: str = ""


class VerifyResponse(ChecklistModel):
    step_id: Annotated[int, Field(ge=1)]
    verdict: Verdict
    confidence: Confidence
    found_counts: dict[str, int]
    expected_counts: dict[str, int]
    issues: list[Issue]
    message: VisualPhrase
    fix_hint: VisualPhrase
    masks: list[OverlayMask]
    latency_ms: Annotated[int, Field(ge=0)] = 0
    next_step_unlocked: bool = False


class VerifyRequest(ChecklistModel):
    session_id: SessionId
    step_id: Annotated[int, Field(ge=1)]
    # Raw base64, no data URL; decoded images are limited to 10 MiB as well.
    image_base64: Annotated[str, Field(min_length=1, max_length=13_981_016)]


class OverrideRequest(ChecklistModel):
    session_id: SessionId
    step_id: Annotated[int, Field(ge=1)]
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class OverrideResponse(ChecklistModel):
    session_id: SessionId
    step_id: int
    status: Literal["PASSED"] = "PASSED"
    passed_via: Literal["override"] = "override"
    reason: str
    next_step_unlocked: bool


class SessionStep(ChecklistModel):
    step_id: int
    status: StepStatus
    passed_via: Literal["automatic", "override"] | None = None
    last_verdict: Verdict | None = None
    retry_count: Annotated[int, Field(ge=0)] = 0


class AuditEntry(ChecklistModel):
    timestamp: str
    event: Literal["session_created", "requirements_reviewed", "step_activated", "check_started", "check_completed", "check_error", "override"]
    step_id: int | None = None
    details: dict = Field(default_factory=dict)


class SessionView(ChecklistModel):
    session_id: SessionId
    created_at: str
    mock_mode: bool
    provider: Literal["meta", "gemini"] = "meta"
    reviewed_at: str | None = None
    checklist: Checklist
    steps: list[SessionStep]
    audit_log: list[AuditEntry]
    complete: bool = False
