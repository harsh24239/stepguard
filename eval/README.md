# Evaluate saved assembly photos

The runner compares a plain visual model prompt with StepGuard's full detection, count, geometry, and guarded judgment pipeline. It never unlocks session steps. Tests of this runner use injected responses and are not accuracy evidence. No physical evaluation has been run yet; `results.md` says so.

1. Use a manual and assembly kit you have permission to photograph. Compile that manual through the app. Save the response from `POST /compile-manual` as `private_assets/evaluation/checklist.json`. Alternatively, save only the `checklist` field from `GET /session/{session_id}`. Do not use the whole session envelope.
2. Put the corresponding photos under `private_assets/evaluation/`. Use fixed overhead framing and the same actual kit. Include correct, missing part, wrong part, wrong place, and blurred/occluded cases. Label each photo before running either model. Prefer at least two independently checked cases in each category. A small sample is a demonstration, not a production accuracy estimate.
3. Create `private_assets/evaluation/cases.json` as a JSON list. Image paths are relative to this manifest and must remain inside its directory. For example:

```json
[
  {"case_id":"correct-01","image":"correct-01.png","step_id":1,"category":"correct","expected_verdict":"pass"},
  {"case_id":"missing-01","image":"missing-01.png","step_id":1,"category":"missing","expected_verdict":"fail"},
  {"case_id":"wrong-part-01","image":"wrong-part-01.png","step_id":1,"category":"wrong_part","expected_verdict":"fail"},
  {"case_id":"wrong-place-01","image":"wrong-place-01.png","step_id":1,"category":"wrong_place","expected_verdict":"fail"},
  {"case_id":"occluded-01","image":"occluded-01.png","step_id":1,"category":"low_confidence","expected_verdict":"unsure"}
]
```

These are manifest examples, not supplied photos or observed labels. Choose the actual step and expected outcome for each assembly. A wrong placement must violate a relation in the compiled checklist. Verify that the compiled counts/relations match the manual before evaluating them. Record any compiler corrections rather than tuning the checklist silently to the evaluation photos.

With your current Gemini demo configuration in `.env`, run from the project root:

```sh
DETECTION_CACHE_SECONDS=0 .venv/bin/python -m eval.baseline_vs_stepguard \
  --checklist private_assets/evaluation/checklist.json \
  --cases private_assets/evaluation/cases.json \
  --output eval/gemini-results.md \
  --allow-gemini-demo
```

After the Meta adapters have been implemented and validated, use `MODEL_PROVIDER=meta`, real Meta configuration, and omit `--allow-gemini-demo`. Changing configuration alone does not implement the Meta adapters. Mock evaluation is refused. Gemini reports are prominently labeled as demo experiments and cannot establish Meta usage.

The output consists of Markdown and a matching JSON file. Use an `.md` output path. The runner validates all inputs before requesting model calls and sends identical normalized pixels to both paths. It records each verdict, latency, agreement with the supplied label, provider errors, and false passes (a pass on any case labeled fail or unsure). Provider errors remain in the denominator. Latency medians exclude errors and include any configured retries. Detection cache duration, retry count, and timeout settings appear in the report; disable the cache for cold-call comparisons.

One case costs a baseline request plus all detection phrases and, when evidence permits, a judge request. Retries and compiler calls cost extra. The default batch cap is 10 cases, controlled by `MAX_CHECKS_PER_MINUTE` (1–120). Use smaller batches to respect provider quotas. This local cap is per run/process, not a distributed provider request limit. Runs are sequential and provider load can affect timing.

Exit codes: `0` means every call completed (it does not mean every label matched), `1` means a report was produced with provider errors, and `2` means input/configuration prevented evaluation. Reports omit media, transcripts, arbitrary provider errors, and input file paths. Review any report before publishing it. Keep manuals and photos in the ignored `private_assets/` directory unless you have explicit sharing rights.
