# StepGuard: Complete Build Prompt

> **Current scope decision (October 27, 2026):** build for the hackathon first. Follow [the active hackathon implementation plan](docs/PRODUCT_IMPLEMENTATION_PLAN.md) for the UI redesign, lightweight checklist review, validation, and delivery order. The broader full-software proposal is deferred. Preserve the contracts and safety/verification gates below. Gemini remains temporarily authorized for development; it does not satisfy required Meta usage, and the intended submitted runtime remains Meta-only. This update adds no claim that pending features are complete.

Give this whole file to your coding agent (Claude Code, Cursor, etc.) and say:
**"Read STEPGUARD_COMPLETE_PROMPT.md. Build it milestone by milestone. Stop after each milestone and tell me how to verify it."**

---

## 0. Context

I am building **StepGuard** for the Meta Global AI Developer Hackathon.

- Building period: Oct 27 to Nov 4, 2026. I will submit by Nov 3. Hard deadline: Nov 4, 9:00 PM ET.
- Theme: **Push the Frontier** (manufacturing).
- Judging: Impact 30%, Use of Meta AI Tooling 25%, Demo 25%, Technical Depth 20%.
- Submission needs: a **public GitHub repo**, a **3-minute demo video**, and a working product judges can see. Everything shown must have been built during the event.

### What StepGuard is

Upload an assembly manual (PDF). A fixed overhead camera watches the workbench. When the worker finishes a step, StepGuard checks the scene, returns **pass / fail / unsure** with a specific message and fix hint (for example "Step 3 wrong: 1 screw missing, top-right"), shows red or green overlays, speaks the feedback, and **keeps the next step locked until the current step passes**.

Pitch: factory visual inspection normally needs thousands of labeled photos per product. StepGuard needs only the manual.

### Platform decision (already made)

Build a **web app**: a FastAPI backend plus a React (Vite) frontend that runs in any modern browser using the laptop webcam. No native mobile or desktop app, no installers, no multi-platform builds. The README must explain how to run it locally in a few commands. Optionally deploy it later if time remains, but local run plus the demo video is the required baseline.

---

## 1. Hard rules (follow always)

1. **Never invent API details.** Meta model names, base URL, request and response formats, and package names must come from the official docs (Quickstart, Model list, API cookbook at the Meta developer portal). All of them live in `.env` and in one file, `backend/meta_client.py`. If unsure, write `TODO(verify in docs)` and ask me to paste the docs snippet. Do not guess SDK or package names.
2. **Meta models only at runtime.** The shipped app must not call OpenAI, Gemini, Claude, or any other model provider, not even as a fallback. While my credits are pending, develop with `MOCK_MODE`. Other AI tools may help *write* the code, and the README should say which.
3. **Built during the event.** Small, frequent commits with clear messages. First commit on or after Oct 27, 2026. No pre-existing project code. Standard scaffolding (Vite, FastAPI starters) is fine; say so in the README.
4. **Rights to assets.** Do not commit third-party manuals, images, or datasets to the public repo. Keep test manuals in `private_assets/` (gitignored). List every third-party library and its license in the README.
5. **No faking.** No hardcoded verdicts in the demo path. `MOCK_MODE` is for development only and the UI must show a visible **MOCK** badge when it is on.
6. **Honest claims.** Say "automatic step checking", never "real-time". No accuracy percentages, no ISO or compliance claims. Call it a prototype.
7. **Secrets.** The API key lives only in `.env`, which is in `.gitignore`. Never print or commit it.
8. **Scope discipline.** Build only what is in section 3. No extra features.

---

## 2. Models and their jobs

Each Meta model must do a real job that cannot be swapped out.

| Model | Job |
|---|---|
| Muse Wonder | Reads the manual PDF and outputs a structured step checklist (JSON) |
| SAM 3.1 | Takes a short noun phrase plus the camera image, returns boxes and masks for parts |
| Muse Spark | Compares SAM findings and geometry results to the step requirements, returns verdict and fix hint |
| Muse Voice Transcribe | Hands-free commands such as "step done" (a button fallback always exists) |
| Muse Spark Open (optional, last) | Same judge call served via Baseten, model id `meta-models/muse-spark-open-1026`, for the open-weights bonus |

Spoken feedback uses the **browser's built-in SpeechSynthesis**. It is not a Meta model and must never be described as one.

Parts of the app that are ordinary code (no AI): webcam view, canvas overlay, motion detector, step lock, counting and geometry rules, audit log, speech output.

---

## 3. Scope

Build only this:

1. Manual PDF to checklist JSON
2. Step check: SAM finds parts, geometry rules count and locate them, Muse Spark gives the verdict
3. Red/green overlay with a specific message
4. Next step stays locked until the current step passes
5. Spoken feedback via browser speech
6. Triggers: "Check step" button, voice command, and automatic trigger when motion stops (hands left the table)

Stretch (only after everything above works): end-of-session report; open-weights judge via Baseten.

Out of scope: accounts, databases, multi-camera, dashboards, mobile or desktop native apps, any compliance claims.

---

## 4. Tech stack and repo structure

- Backend: Python 3.11+, FastAPI, pydantic, httpx (or the official SDK if the docs specify one), Pillow, numpy.
- Frontend: React + Vite + TypeScript + Tailwind, canvas overlay.
- Config `.env.example`:

```
META_API_KEY=
META_BASE_URL=
MODEL_WONDER=
MODEL_SPARK=
MODEL_SAM=
MODEL_VOICE=
MODEL_SPARK_OPEN=meta-models/muse-spark-open-1026
BASELINE_URL=
USE_OPEN_WEIGHTS=false
MOCK_MODE=true
```

- No database. Session state in memory; audit log written to `sessions/<id>.json`.

```
stepguard/
  README.md
  .env.example
  .gitignore                 # includes .env and private_assets/
  backend/
    main.py                  # FastAPI app
    meta_client.py           # ALL Meta API calls live here
    compiler.py              # manual PDF -> checklist
    inspector.py             # SAM calls + geometry checks
    judge.py                 # verdict + fix hint
    state.py                 # step state machine + lock
    schemas.py
    fixtures/                # mock responses (dev only)
  frontend/src/
    App.tsx
    components/{CameraView,Checklist,FeedbackPanel,AuditLog}.tsx
    lib/{speech,motion}.ts
  scripts/day1_sam_test.py
  eval/baseline_vs_stepguard.py
  private_assets/            # gitignored: manuals, test photos you don't have rights to share
  sessions/
```

### The one file that talks to Meta (`meta_client.py`)

It must expose exactly these functions. The rest of the app calls only these. Each does `if MOCK_MODE: return fixture`, otherwise the real call.

```python
def compile_manual(pdf_bytes: bytes) -> dict: ...        # Muse Wonder -> checklist JSON
def segment(image_bytes: bytes, prompt: str) -> list[dict]: ...  # SAM 3.1 -> [{label, box, score, mask_png_base64}]
def judge(step: dict, found: dict, geometry: dict, annotated_image: bytes) -> dict: ...  # Muse Spark -> strict JSON
def transcribe(audio_bytes: bytes, mime: str) -> str: ... # Muse Voice Transcribe
```

---

## 5. Data contracts

### Checklist JSON (from `compile_manual`)

```json
{
  "product": "string",
  "steps": [
    {
      "step_id": 1,
      "instruction": "Attach the base plate",
      "sam_prompts": ["yellow plate", "black pin"],
      "expected_counts": {"yellow plate": 1, "black pin": 4},
      "zone_anchor": "yellow plate",
      "spatial_rules": [{"part": "black pin", "relation": "inside", "target": "yellow plate"}],
      "fix_hint_template": "Place the black pins into the holes on the yellow plate."
    }
  ]
}
```

Compiler prompt rules for Muse Wonder:
- Convert technical part names into **visual primitives** SAM can find ("silver screw", "red beam", "black wheel"), not serial numbers.
- Always include a `zone_anchor` (main board, chassis, or base).
- Output strict JSON only. Validate with pydantic; retry once with the validation error if invalid.

### `POST /verify-step`

Request: `{session_id, step_id, image_base64}`. Response:

```json
{
  "step_id": 3,
  "verdict": "pass | fail | unsure",
  "confidence": 0.0,
  "found_counts": {"silver screw": 3},
  "expected_counts": {"silver screw": 4},
  "issues": [{"type": "missing | wrong_part | misplaced | low_confidence",
              "part": "silver screw", "location_hint": "top-right",
              "message": "1 screw missing at top-right"}],
  "fix_hint": "Add one screw at the top-right corner.",
  "masks": [{"label": "silver screw", "box": [0,0,0,0], "status": "ok|bad", "mask_png_base64": ""}],
  "latency_ms": 0,
  "next_step_unlocked": false
}
```

Other endpoints: `POST /compile-manual`, `POST /transcribe`, `GET /session/{id}`, `POST /override` (supervisor override, logged with reason and time).

---

## 6. Verification logic

1. Run SAM for the step's `zone_anchor` first. If not found, return `unsure`: "Can't see the assembly area. Check camera and lighting."
2. Run SAM for each part prompt. Keep only masks whose centroid is inside the anchor's bounding box (zone gating), unless a rule says outside.
3. Deterministic geometry in Python: count instances per prompt; check `inside`, `left_of`, `above`, and quadrant rules using boxes, centroids, and IoU. Drop masks below a minimum area; merge near-duplicate masks (high IoU) so one part is not counted twice.
4. Send compact found-vs-expected JSON plus the annotated image to Muse Spark. It returns verdict, issues, and fix hint as strict JSON. **The judge may downgrade to `unsure`, but may never turn a deterministic count failure into a pass.**
5. **Confidence rule:** if counts are ambiguous or scores are low, return `unsure` and show amber "Please check Step N (low confidence)". Never show a loud red failure when unsure.
6. A step passes only if counts match, rules hold, and there are no issues. Only then unlock the next step.

State machine: `LOCKED -> ACTIVE -> CHECKING -> PASSED | FAILED | UNSURE`. FAILED or UNSURE returns to ACTIVE on the next check. Step N+1 stays LOCKED until step N is PASSED.

Feedback messages to implement for each issue type:
- missing: "Step N is wrong: {count} {part} missing, {location}."
- wrong_part: "Step N is wrong: {found} is where {expected} should be. Swap them."
- misplaced: "Step N is wrong: {part} is in the wrong place. Move it {direction}."
- unsure: "Please check Step N (low confidence)."

---

## 7. Frontend behavior

- Layout: camera plus overlay on the left; checklist (locked, active, passed) top-right; feedback panel and audit log bottom-right. Dark theme.
- Overlay: green for ok parts, red for bad parts, dashed yellow box where a missing part belongs, amber banner for unsure.
- On fail: banner "STEP N BLOCKED", the message, and the fix hint. Speak the message once with `speechSynthesis`; include a mute toggle.
- Auto trigger (`motion.ts`): compute frame differences on a downscaled canvas. When motion is high then drops below a threshold for about 0.7 s, capture one frame and call `/verify-step`. Add a cooldown so it does not re-trigger while a result is displayed.
- Voice: hold the mic button to record a short clip, send it to `/transcribe`, match commands ("step done", "check step", "next step"). The button is always available as fallback.
- Show the latency of each check ("checked in 3.2 s"). Do not call it real-time.

---

## 8. Milestones (stop after each)

Phase A: build with `MOCK_MODE=true` (works before credits arrive)

- **M1: Setup.** Repo, `.env.example`, `.gitignore`, `meta_client.py` with the four functions returning fixtures, FastAPI skeleton, Vite app that loads.
- **M2: Compiler endpoint.** `POST /compile-manual` returns a validated checklist (fixture in mock mode).
- **M3: Inspector.** Zone gating, counting, and geometry rules, with unit tests on fixture masks.
- **M4: Judge and state machine.** Verdicts, fix hints, confidence handling, step lock, override log.
- **M5: UI.** Camera, overlay, checklist, feedback panel, spoken feedback, button trigger.
- **M6: Auto trigger and voice.** Motion detector and transcribe flow.

Phase B: plug in the real Meta API

Before this phase, ask me to paste these from the official docs (do not guess):

```
BASE URL:
AUTH:
EXACT MODEL NAMES (Wonder, Spark, SAM 3.1, Voice Transcribe):
EXAMPLE REQUEST: text + image (Spark):
EXAMPLE REQUEST: PDF input (Wonder):
EXAMPLE REQUEST + RESPONSE FORMAT: SAM 3.1 (noun phrase + image):
EXAMPLE REQUEST: audio transcription:
RATE LIMITS / ERROR NOTES:
```

- **M7: SAM first (go or no-go).** Implement real `segment()`. Run `scripts/day1_sam_test.py` on one overhead photo of 5 distinct parts; print found or not, mask count, and score per phrase. Report to me. If fewer than 4 of 5 are found, stop and tell me (we change the parts, not the idea).
- **M8: Real compiler.** Implement `compile_manual()` with Muse Wonder on a manual in `private_assets/`. Show me the checklist for review.
- **M9: Real judge.** Implement `judge()` with Muse Spark using strict JSON output. Test with three saved images: correct, missing part, wrong part.
- **M10: Real voice.** Implement `transcribe()` and test "step done".
- **M11: Real mode.** Set `MOCK_MODE=false`. Run the whole flow on the real kit: correct assembly for 3 steps, then a wrong part: red overlay, spoken hint, next step locked, fix, green.
- **M12: Reliability and cost.** Timeouts (about 30 s) and at most 2 retries; "Checking again..." in the UI. Never call SAM per video frame. Cache results by image hash. Log latency per call. Add a max-checks-per-minute setting.
- **M13: Evidence.** `eval/baseline_vs_stepguard.py`: for a folder of test images (correct, missing, wrong part, wrong place), run (a) a plain Muse Spark or Wonder prompt "does this match step N?" and (b) the full StepGuard pipeline. Save a table to `eval/results.md`. Report real results only, even if unflattering.
- **M14: README and clean-up.** README sections: what it is, how to run in a few commands, which model does what, **"Built during the hackathon"**, limitations (prototype, not real-time, tested on one kit), tools that helped write the code, licenses. Then run the clean-up checks below.
- **M15 (stretch): Open weights.** If `USE_OPEN_WEIGHTS=true`, `judge()` calls `MODEL_SPARK_OPEN` through `BASELINE_URL` (Baseten). Say so in the README and the video.

### Clean-up checks (run before submitting)

```bash
grep -riE "openai|anthropic|gemini|generativelanguage|cohere|mistral" \
  --include=*.py --include=*.ts --include=*.tsx --include=*.json . \
  --exclude-dir=node_modules --exclude-dir=.git || echo "OK: no other providers"

git log -p | grep -iE "api[_-]?key|secret|bearer" || echo "OK: no keys in history"
```

If a key was ever committed, rotate it in the Meta portal and clean the history before the repo goes public.

---

## 9. Acceptance checklist (before recording the demo)

- [ ] Real PDF manual in, valid checklist out
- [ ] `MOCK_MODE=false`, no MOCK badge visible
- [ ] Correct assembly gives green for 3 consecutive steps, with no false alarms in 5 full runs
- [ ] A wrong or missing part gives red, a spoken message, and the next step stays locked
- [ ] Fixing it gives green and unlocks the next step
- [ ] Low-confidence case shows amber, not red
- [ ] `eval/results.md` has real numbers
- [ ] No other AI provider in the repo; no keys in git
- [ ] README states what was built during the hackathon and what is prototype

## 10. Demo script (3 minutes)

- 0:00 to 0:30: the problem (labeled-photo inspection is too costly for small factories)
- 0:30 to 1:00: upload the manual, checklist appears
- 1:00 to 2:00: correct assembly, green overlays, steps unlock
- 2:00 to 2:40: wrong part, red overlay, spoken fix hint, next step locked; fix it, green
- 2:40 to 3:00: baseline vs StepGuard table, then the commit history

Say aloud or show on screen what was built during the hackathon.

## 11. Submission checklist (my tasks, not the agent's)

- [ ] I claimed my own Meta API credits (form, credit card on file) before Nov 4, 9:00 PM ET
- [ ] Repo is public and opens in a logged-out window
- [ ] Demo video is 3 minutes and the link opens without login
- [ ] Everyone who worked on it is listed; one Representative submits one project
- [ ] Submitted by Nov 3

---

**Start with M1.** Ask me for anything you need before writing code.
