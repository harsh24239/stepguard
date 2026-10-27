"""Apply a validated Meta judgment without weakening deterministic inspection."""

from pydantic import ValidationError

from backend import meta_client
from backend.inspector import InspectionResult
from backend.schemas import ChecklistStep, Issue, JudgeOutput, OverlayMask, VerifyResponse

MIN_JUDGE_CONFIDENCE = 0.7  # Development threshold; not a calibrated probability.


def _issue(kind: str, part: str, message: str, location="assembly area") -> Issue:
    return Issue(type=kind, part=part, location_hint=location, message=message)


def _deterministic_feedback(step: ChecklistStep, evidence: InspectionResult) -> tuple[list[Issue], str]:
    issues = [Issue.model_validate(item) for item in evidence.issues]
    fix_hint = step.fix_hint_template
    for check in evidence.count_checks:
        delta = check["expected"] - check["found"]
        part = check["part"]
        if delta > 0:
            message = f"Step {step.step_id} is wrong: {delta} {part} missing, assembly area."
            issues = [item.model_copy(update={"message": message}) if item.type == "missing" and item.part == part
                      else item for item in issues]
            fix_hint = f"Add {delta} {part} to the assembly area."
            break
        if delta < 0:
            fix_hint = f"Remove {-delta} extra {part} from the assembly area."
            break
    for check in evidence.rule_checks:
        if check["holds"]:
            continue
        relation = check["relation"].replace("_", "-")
        target = check["target"]
        direction = {"inside": f"inside {target}", "outside": f"outside {target}",
                     "left_of": f"to the left of {target}", "above": f"above {target}"}.get(
                         check["relation"], f"to the {relation} quadrant of {target}")
        message = f"Step {step.step_id} is wrong: {check['part']} is in the wrong place. Move it {direction}."
        issues = [item.model_copy(update={"message": message}) if item.type == "misplaced" and item.part == check["part"]
                  else item for item in issues]
        if evidence.counts_match:
            fix_hint = f"Move {check['part']} {direction}."
        break
    return issues, fix_hint


def judge_step(step: ChecklistStep, evidence: InspectionResult) -> VerifyResponse:
    if evidence.step_id != step.step_id or evidence.expected_counts != step.expected_counts:
        raise ValueError("Inspection evidence does not belong to this step")
    issues, deterministic_hint = _deterministic_feedback(step, evidence)
    deterministic_pass = (evidence.deterministic_checks_pass
                          and evidence.found_counts == step.expected_counts)
    model = None
    if not evidence.uncertain and evidence.counts_match is not None and evidence.rules_hold is not None:
        found = {"found_counts": evidence.found_counts, "expected_counts": evidence.expected_counts}
        geometry = {"counts_match": evidence.counts_match, "rules_hold": evidence.rules_hold,
                    "count_checks": evidence.count_checks, "rule_checks": evidence.rule_checks,
                    "issues": [item.model_dump() for item in issues]}
        raw = meta_client.judge(step.model_dump(), found, geometry, evidence.annotated_image)
        try:
            model = JudgeOutput.model_validate(raw)
        except ValidationError:
            issues.append(_issue("low_confidence", step.zone_anchor, "The judge returned an invalid response. Check this step again."))

    if model:
        issues.extend(item for item in model.issues if item not in issues)
    confidence = min(model.confidence, min((item.score for item in evidence.detections), default=0.0)) if model else 0.0
    uncertain = (evidence.uncertain or evidence.counts_match is None or evidence.rules_hold is None
                 or model is None or model.verdict == "unsure" or confidence < MIN_JUDGE_CONFIDENCE
                 or any(item.type == "low_confidence" for item in issues)
                 or (model.verdict == "fail" and not model.issues and deterministic_pass))
    if uncertain:
        verdict = "unsure"
        if not any(item.type == "low_confidence" for item in issues):
            issues.append(_issue("low_confidence", step.zone_anchor, "The available evidence is not sufficient to pass this step."))
        message = f"Please check Step {step.step_id} (low confidence)."
        fix_hint = (model.fix_hint if model and model.verdict == "unsure"
                    else "Check camera and lighting, then check this step again.")
        if evidence.counts_match is None and issues:
            fix_hint = issues[-1].message
    elif not deterministic_pass or model.verdict == "fail" or issues:
        verdict = "fail"
        if not issues:
            issues.append(_issue("wrong_part", step.zone_anchor, "The deterministic requirements for this step are not satisfied."))
        message = issues[0].message
        if not message.startswith(f"Step {step.step_id}"):
            message = f"Step {step.step_id} is wrong: {message}"
        fix_hint = deterministic_hint if not deterministic_pass else model.fix_hint
    else:
        verdict = "pass"
        message = f"Step {step.step_id} passed."
        fix_hint = "Continue to the next step."

    bad_parts = {item.part for item in issues if item.type != "low_confidence"}
    masks = [OverlayMask(label=item.label, box=item.box,
                         status="bad" if verdict == "fail" and item.label in bad_parts else "ok",
                         mask_png_base64=item.mask_png_base64) for item in evidence.detections]
    return VerifyResponse(step_id=step.step_id, verdict=verdict, confidence=confidence,
                          found_counts=evidence.found_counts, expected_counts=step.expected_counts,
                          issues=issues, message=message, fix_hint=fix_hint, masks=masks)
