"""Compare a plain visual prompt with the guarded pipeline on labeled photos.

Run from the repository root with python -m eval.baseline_vs_stepguard --help.
Labels must come from a human inspecting each actual assembly, before running.
"""

import argparse
from datetime import datetime, timezone
import io
import json
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Annotated, Literal

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from backend import meta_client
from backend.inspector import InspectorConfig, decode_image, inspect_step
from backend.judge import judge_step
from backend.model_errors import ModelError
from backend.runtime import CheckLimiter, setting
from backend.schemas import Checklist, JudgeOutput


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    case_id: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,60}$")]
    image: Annotated[str, StringConstraints(min_length=1)]
    step_id: Annotated[int, Field(ge=1)]
    category: Literal["correct", "missing", "wrong_part", "wrong_place", "low_confidence"]
    expected_verdict: Literal["pass", "fail", "unsure"]


def load_cases(checklist_path: Path, manifest_path: Path):
    checklist = Checklist.model_validate_json(checklist_path.read_text())
    raw = json.loads(manifest_path.read_text())
    if not isinstance(raw, list) or not 1 <= len(raw) <= 100:
        raise ValueError("Supply a JSON list containing 1 to 100 labeled cases.")
    cases = [Case.model_validate(case) for case in raw]
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("Case IDs must be unique.")
    root = manifest_path.resolve().parent
    prepared = []
    for case in cases:
        if case.step_id > len(checklist.steps):
            raise ValueError("A case references an unknown checklist step.")
        path = (root / case.image).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("Case images must be local files inside the manifest directory.")
        with path.open('rb') as stream:
            data = stream.read(10 * 1024 * 1024 + 1)
        if len(data) > 10 * 1024 * 1024:
            raise ValueError("Case image exceeds 10 MiB.")
        image = decode_image(data, InspectorConfig())
        # The exact same decoded pixels reach baseline and full pipeline.
        output = io.BytesIO()
        image.save(output, format="PNG")
        prepared.append((case, checklist.steps[case.step_id - 1], output.getvalue()))
    return prepared


def evaluate(prepared, *, allow_gemini_demo=False):
    if meta_client.MOCK_MODE:
        raise ValueError("Evaluation refuses MOCK mode. Fixture results are not physical evidence.")
    if meta_client.MODEL_PROVIDER != "meta" and not allow_gemini_demo:
        raise ValueError("Use --allow-gemini-demo to label this as a Gemini experiment, not Meta evidence.")
    if len(prepared) > setting("MAX_CHECKS_PER_MINUTE", 10, 1, 120):
        raise ValueError("Batch exceeds MAX_CHECKS_PER_MINUTE. Use a smaller batch or configure a suitable limit.")
    limiter = CheckLimiter()
    rows = []
    for case, step, image in prepared:
        limiter.reserve()
        row = {"case_id": case.case_id, "step_id": case.step_id, "category": case.category,
               "expected_verdict": case.expected_verdict}
        for name, invoke in (
            ("baseline", lambda: JudgeOutput.model_validate(meta_client.baseline(step.model_dump(), image))),
            ("stepguard", lambda: judge_step(step, inspect_step(step, image))),
        ):
            started = perf_counter()
            try:
                result = invoke()
                row[name] = {"verdict": result.verdict, "latency_ms": round((perf_counter() - started) * 1000)}
            except (ModelError, NotImplementedError, ValidationError):
                # Never save arbitrary provider messages, raw model output, or media.
                row[name] = {"verdict": "error", "latency_ms": round((perf_counter() - started) * 1000)}
        rows.append(row)
    report = {"provider": meta_client.MODEL_PROVIDER, "mock_mode": False,
              "measured_at": datetime.now(timezone.utc).isoformat(), "cases": rows,
              "runtime": {"detection_cache_seconds": setting("DETECTION_CACHE_SECONDS", 30, 0, 300),
                          "max_retries": setting("MODEL_MAX_RETRIES", 2, 0, 2),
                          "timeout_seconds": setting("MODEL_TIMEOUT_SECONDS", 30, 5, 60)},
              "limitations": "Human-labeled photos; small sample; not production accuracy or session progression evidence."}
    for name in ("baseline", "stepguard"):
        completed = [row[name]["latency_ms"] for row in rows if row[name]["verdict"] != "error"]
        report[name] = {
            "agreements": sum(row[name]["verdict"] == row["expected_verdict"] for row in rows),
            "total_cases": len(rows),
            "errors": sum(row[name]["verdict"] == "error" for row in rows),
            "false_passes": sum(row[name]["verdict"] == "pass" and row["expected_verdict"] != "pass" for row in rows),
            "median_latency_ms": median(completed) if completed else None,
        }
    return report


def markdown(report):
    label = "GEMINI DEMO EXPERIMENT" if report["provider"] == "gemini" else "META EXPERIMENT"
    lines = ["# Baseline vs StepGuard", "", label, "", f"Measured: {report['measured_at']}", "",
             report["limitations"], "", "Errors remain in the denominator. Latency medians exclude errors.", ""]
    lines.extend(["Runtime controls: " + json.dumps(report["runtime"], sort_keys=True), "",
                  "Disable detection caching for cold-call timing comparisons. Calls run sequentially; "
                  "latencies include configured retries and are subject to provider load.", ""])
    for name in ("baseline", "stepguard"):
        stats = report[name]
        latency = stats["median_latency_ms"]
        lines.append(f"- {name}: {stats['agreements']}/{stats['total_cases']} label agreements; "
                     f"{stats['errors']} errors; {stats['false_passes']} false passes; "
                     f"median completed latency: {str(latency) + ' ms' if latency is not None else 'not available'}.")
    lines.extend(["", "| Case | Category | Expected | Baseline | StepGuard | Baseline ms | StepGuard ms |",
                  "| --- | --- | --- | --- | --- | --- | --- |"])
    for row in report["cases"]:
        lines.append(f"| {row['case_id']} | {row['category']} | {row['expected_verdict']} | "
                     f"{row['baseline']['verdict']} | {row['stepguard']['verdict']} | "
                     f"{row['baseline']['latency_ms']} | {row['stepguard']['latency_ms']} |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checklist", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("eval/results.md"))
    parser.add_argument("--allow-gemini-demo", action="store_true")
    args = parser.parse_args()
    try:
        if args.output.suffix != ".md":
            raise ValueError("Use an .md output path; the accompanying JSON needs a distinct path.")
        prepared = load_cases(args.checklist, args.cases)
        targets = [args.output, args.output.with_suffix(".json")]
        sources = {args.checklist.resolve(), args.cases.resolve()}
        sources.update((args.cases.resolve().parent / case.image).resolve() for case, _, _ in prepared)
        for target in targets:
            if target.is_symlink() or target.resolve() in sources:
                raise ValueError("Report paths cannot overwrite an input or a symlink.")
        report = evaluate(prepared, allow_gemini_demo=args.allow_gemini_demo)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown(report))
        args.output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
        print("Evaluation saved; provider:", report["provider"], "cases:", len(report["cases"]))
        return 1 if any(report[name]["errors"] for name in ("baseline", "stepguard")) else 0
    except (OSError, ValueError, ModelError):
        print("Evaluation could not complete. Check real-mode configuration, local case files, labels, and check limits. No measured report was produced.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
