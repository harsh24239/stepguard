# StepGuard

[Public repository](https://github.com/harsh24239/stepguard) · [Offline release checks](https://github.com/harsh24239/stepguard/actions/workflows/checks.yml)

StepGuard is a prototype for automatic assembly step checking, built for the Meta Global AI Developer Hackathon's manufacturing theme. The intended workflow is to upload an assembly manual, check a workbench image against each step, and keep the following step locked until the current one passes.

**Current milestone: M6 — motion-stop and recorded voice triggers implemented.** Upload a PDF, review the extracted requirements, select **Start inspection**, explicitly enable the webcam, then use **Check step**, enable **Check when motion stops**, or hold **Hold to speak**. Every trigger checks the current server step through the same verification flow. The workspace shows the checklist, captured-frame overlays, feedback, browser speech, and audit log. Later steps stay locked until a server-confirmed pass or a reason-required manual override. All model calls remain fixture-backed in mock mode: the judge returns **unsure** and transcription returns **step done** regardless of the recorded speech. No real assembly has been inspected.

**Temporary Gemini demo:** Gemini now implements PDF compilation, image detection, visual judging, and recorded transcription through the same four-function boundary. This is an explicitly authorized demo addition to the original Meta-only plan. See the setup below. It has been tested with intercepted HTTP responses; a live API call and physical-kit validation remain pending.

**Remaining work:** the five-phrase SAM harness, reliability controls, and baseline evaluation runner are implemented. Official Meta API docs have now been reviewed, but the Meta adapters and physical-kit evaluation remain pending. Health continues to report M6 because the live Meta acceptance gates have not passed. See [hackathon readiness](docs/HACKATHON_READINESS.md) for the verified rules and blockers, [evaluation instructions](eval/README.md), and the [three-minute demo plan](docs/DEMO_SCRIPT.md).

**Operator workflow update (October 27):** The focused UI and server-enforced requirements review are implemented. A pass or manual override preserves its checked step until **Continue**; voice/motion cannot check the next step during that hold. History, step details, and optional triggers are collapsed by default. All live Meta and physical-kit gates remain pending. See [current validation and handoff](docs/NEXT_DAY_VALIDATION.md) and [verification record](docs/UI_VERIFICATION.md).

**Design update:** The local prototype now uses the precision-workbench visual system, with PDF drag-and-drop, a custom assembly illustration, an in-app workflow guide, and a server-derived step map. See [design and verification notes](docs/DESIGN_UPDATE.md).

**Active implementation scope:** follow the [hackathon implementation plan](docs/PRODUCT_IMPLEMENTATION_PLAN.md): verified Meta integration, a focused operator UI, lightweight checklist review, one validated physical kit, and submission evidence. Accounts, databases, team dashboards, and the wider product roadmap are deferred until after the event. The plan remains the scope reference; the workflow update above records the newly completed local work.

## Complete local release (no API key needed)

Prerequisites: Python **3.12+**, Node.js **22.12+**, and npm. From the project root:

```sh
python3 scripts/project.py setup
python3 scripts/project.py check
python3 scripts/project.py run --build
```

Open **http://127.0.0.1:8000**. The built React application and FastAPI run from
one origin; no Vite server is required. If port 8000 is already in use, add
`--port 8001` to the run command. The local prototype is unauthenticated and
binds to localhost by default. API documentation is at **/api/docs**.

Setup preserves an existing `.env`. For an explicitly offline rehearsal, prefix
the run command with `MOCK_MODE=true MODEL_PROVIDER=meta`. In mock mode, choose
**Try the sample checklist** to start without a PDF or API request. Acknowledge
that it is a development fixture before inspection. It never simulates an
automatic pass; mock checks remain unsure.

**Download report** exports the recorded checklist, review acknowledgment,
provider/mode, check outcomes, errors, and override history as JSON. It excludes
media and configured credentials. Mock fixtures and manual overrides stay labeled;
workflow counts are not accuracy measurements. Do not publish reports containing
manual text or operator reasons without reviewing their contents.

Browser commands are converted locally to **mono 16-bit PCM WAV at 16 kHz** before
transcription. Conversion uses browser decoding/downmixing/resampling; failures
retain the button fallback. Real microphone and live transcription validation
remain pending.

The same offline verification command runs in `.github/workflows/checks.yml`.
It checks dependencies, backend/frontend tests, production build, the built
single-server workflow, and the source-package allowlist without paid model calls.
See [release status](docs/RELEASE_STATUS.md) for completed work and remaining gates.

## Run locally (development)

Prerequisites: Python **3.12+** (tested with 3.12.5), Node.js **22.12+**, and npm. These commands assume macOS/Linux and run from the project root unless indicated. The pinned NumPy version requires Python 3.12 or newer.

Start the backend in one terminal:

```sh
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.lock
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

If `.env` already exists, keep it instead of copying over it. No API key is needed for mock development; `MOCK_MODE=true` is the default. Environment variables already set in the terminal take precedence over `.env`. Restart the backend after changing configuration.

Start the frontend in a second terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open **http://127.0.0.1:5173**. The page should show **Backend connected**, a visible **MOCK** badge, and the upload screen. The header refresh button (**Check backend connection**) repeats the health request. With the backend stopped, the page shows an offline state. Use **Choose PDF**, review every extracted step, acknowledge the checklist, select **Start inspection**, then **Enable camera**; the camera never starts automatically.

Vite proxies `/api/*` to the local backend, removing the `/api` prefix. No broad CORS allowance is needed. The backend's interactive API documentation is at **http://127.0.0.1:8000/docs**.

`npm run build` checks TypeScript and builds static assets. `npm run preview` previews those static assets only; use `npm run dev` for the connected local workspace. For the connected built release, use `python3 scripts/project.py run --build`; it serves the frontend and `/api` together. Public cloud hosting is not configured.

## Enable the Gemini demo

Edit the project-root `.env` locally, keeping your key out of chat and source control:

```env
MOCK_MODE=false
MODEL_PROVIDER=gemini
GEMINI_API_KEY=your_local_gemini_key
GEMINI_MODEL=gemini-3.8-flash
```

Obtain your key from [Google AI Studio](https://aistudio.google.com/apikey). Select a model available to your project that supports PDF, image, audio, and structured JSON input/output. The default model is configurable; an unavailable model produces an error rather than a fixture fallback. The adapter uses the documented [generateContent REST API](https://ai.google.dev/api/generate-content), [PDF input](https://ai.google.dev/gemini-api/docs/document-processing), [image detection coordinates](https://ai.google.dev/gemini-api/docs/image-understanding), and [audio input](https://ai.google.dev/gemini-api/docs/audio).

Restart the backend and refresh the frontend connection. The badge should read **GEMINI DEMO**. Upload a fresh assembly PDF, enable the camera, and check a step. Restarting clears in-memory sessions, so upload again instead of reusing an old session. Recorded commands use Gemini transcription; browser speech still reads feedback aloud locally.

`/health` reports `provider: "gemini"`, `mock_mode: false`, and `model_adapters_ready: true` when a key and syntactically valid model name are configured. This checks configuration only: it does not authenticate the key, check quota/model availability, or measure model accuracy. A missing key shows **GEMINI · NOT READY** and disables model actions. `MOCK_MODE=true` always wins, even with Gemini selected: inputs are then ignored by the fixture adapters and the UI remains **MOCK**.

The demo sends your uploaded PDF, captured check images, and submitted audio clips to Google's Gemini API. Credentials stay on the backend; requests use header authentication. Raw media and transcripts are not stored in session audits. Session data and audit snapshots identify the selected provider and whether fixtures were used. Gemini returns **bounding boxes, not SAM segmentation masks**. Its confidence values are uncalibrated estimates; existing count/geometry checks and server step locks still apply. Invalid output cannot become a valid pass, and provider failures leave the current step available for retry without unlocking the next one. There is no silent provider switch or fixture fallback. Transient network, timeout, rate-limit, and server failures have at most two automatic retries; authentication and invalid-output failures are not retried.

Quota/rate-limit failures return **429**, authentication/configuration/network failures return **503**, timeouts return **504**, and malformed or unsupported provider output returns **502** with a sanitized message. Each check detects the anchor and other part phrases before asking for a judgment, so one check can use several Gemini requests; latency and quota use depend on the checklist.

When Meta becomes available, implement and validate its four adapters in `backend/meta_client.py`, then set `MODEL_PROVIDER=meta` with `MOCK_MODE=false` and the verified Meta configuration. The UI, workflow endpoints, geometry, and step locks keep the same contracts. **Changing the flag alone does not implement the pending Meta adapters.** The M7 SAM gate refuses Gemini in real mode because Gemini boxes cannot establish a SAM result.

## Reliability, evaluation, and connection checks

The backend defaults to a 30-second timeout per model attempt and at most two retries with bounded backoff for transient errors. A whole step may take longer because it detects multiple phrases and then judges the evidence. Authentication, invalid detections, and malformed output are not retried. Compiler validation has one separate repair request. During verification the UI polls transient retry progress and shows **Checking again** after an actual retry; the next step stays locked.

`DETECTION_CACHE_SECONDS=30` caches normalized detections for identical image bytes, phrase, and provider configuration in bounded process memory. Verdicts are never cached. Set it to `0` for fresh detections or fair evaluation timing. `MAX_CHECKS_PER_MINUTE=10` caps paid verification attempts across sessions in one backend process, returning **429** with the step available for retry. This is a step-check cap, not a provider-wide request limit; compilation, transcription, and separate evaluation processes have their own cost. `MODEL_TIMEOUT_SECONDS` accepts 5–60 and `MODEL_MAX_RETRIES` accepts 0–2. Logs contain only provider, operation, attempt, status, and latency; configure the Python `stepguard.models` logger at INFO to display them.

Check configuration without printing your key:

```sh
.venv/bin/python -m scripts.check_provider
```

To make one tiny Gemini request without media (uses a small amount of quota):

```sh
.venv/bin/python -m scripts.check_provider --live
```

A successful check verifies only basic model access. Use the actual PDF, kit images, and recorded command to verify the complete demo. Follow [eval/README.md](eval/README.md) for labeled baseline-versus-pipeline runs. No measured physical results exist yet; mock results never count as evidence.

Run the complete offline regression suite with fixtures selected explicitly, even if your `.env` selects Gemini:

```sh
MOCK_MODE=true MODEL_PROVIDER=meta MODEL_MAX_RETRIES=0 DETECTION_CACHE_SECONDS=0 .venv/bin/python -m unittest discover -s backend/tests
cd frontend
npm test
npm run build
```

## Verify the setup (M1)

1. Start both servers and confirm the connected state and **MOCK** badge at the frontend URL above.
2. Open `http://127.0.0.1:8000/health`. Expect `status: "ok"`, `mock_mode: true`, `milestone: "M6"`, and `model_adapters_ready: false`. Health means the server is available; it does not mean real model adapters exist.
3. Check the four fixture functions from the root with the virtual environment activated:

   ```sh
   python - <<'PY'
   from backend.meta_client import compile_manual, segment, judge, transcribe
   print(compile_manual(b"")["product"])
   print("Pins:", len(segment(b"", "black pin")))
   print("Verdict:", judge({}, {}, {}, b"")["verdict"])
   print("Command:", transcribe(b"", "audio/webm"))
   PY
   ```

   Expect the development product name, `Pins: 4`, `Verdict: unsure`, and `Command: step done`. Inputs are intentionally unused in mock mode. These outputs are development fixtures, not inspection results.
4. Run `cd frontend && npm run build`. It should pass TypeScript checking and produce `frontend/dist/`.
5. Stop the backend and click the header connection button. The page should show **Backend offline** and disable backend actions. A previously known MOCK badge remains visible; an initial failed connection shows **MODE UNKNOWN**. Restart the backend and check again to restore the connected state.

## Verify M2: compiler endpoint

Update backend dependencies, then restart the backend:

```sh
source .venv/bin/activate
python -m pip install -r backend/requirements.lock
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Put a PDF you have permission to use in `private_assets/`, then upload it from another terminal:

```sh
curl -i http://127.0.0.1:8000/compile-manual \
  -F 'file=@private_assets/manual.pdf;type=application/pdf'
```

Expect **HTTP 200**, **`X-StepGuard-Mode: MOCK`**, **`Cache-Control: no-store`**, and a JSON checklist for `Development fixture: plate and pins`. It has two steps: place the yellow plate, then place four black pins. The response body follows the build prompt's `{product, steps}` contract directly, without an envelope. This is fixture output; the document's contents are not read by a model in mock mode.

Alternatively, open **http://127.0.0.1:8000/docs**, expand **POST /compile-manual**, select **Try it out**, and choose a PDF in the `file` field. The React workspace also supports this upload through **Choose PDF**.

Upload errors are explicit: a missing file returns **422**, an empty file or missing `%PDF-` header returns **400**, a media type other than `application/pdf` returns **415**, and a file larger than **10 MiB** returns **413**. M2 checks the PDF header and media type only; it does not parse or validate the full PDF structure. Uploaded PDFs are closed after every request and are not saved as project assets or session files; multipart processing may temporarily spool uploads to the system's temporary directory.

Checklist validation rejects blank required text, extra fields, empty checklists, invalid step order, duplicate SAM prompts, missing or unknown counts, negative/non-integer counts, absent anchors, and spatial rules referencing unknown parts. Each prompt must have an expected count; the anchor must have a positive expected count. Step IDs must start at 1 and be consecutive. Supported relation names are `inside`, `outside`, `left_of`, `above`, `top_left`, `top_right`, `bottom_left`, and `bottom_right`; their geometry is implemented in M3. Structural validation cannot establish whether a phrase is visually useful to SAM or whether a checklist correctly represents a manual.

Invalid compiler output returns **502** with validation locations and messages, excluding model input and exception context. With `MOCK_MODE=false` and `MODEL_PROVIDER=meta`, compilation returns **503** because the real Wonder adapter is pending. With `MODEL_PROVIDER=gemini`, the uploaded PDF is sent to Gemini and the returned checklist must pass the same validation. The Gemini compiler includes one validation-repair request using the original PDF and safe validation errors. The Meta equivalent remains part of M8.

Run the automated checks without starting a server:

```sh
.venv/bin/python -m unittest backend.tests.test_compiler -v
```

The 12 compiler tests cover the multipart endpoint, the checklist contract (including 20 invalid-checklist cases), error responses, private-input omission, and real-mode rejection without loading fixtures. Tests construct an original PDF in memory; no private or third-party assets are needed.

## Verify M3: deterministic inspector

No server, API key, or camera is needed for this development check. Run from the project root:

```sh
.venv/bin/python -m unittest discover -s backend/tests -v
.venv/bin/python -m scripts.inspect_fixture --output private_assets/m3-inspection.png
```

The full suite now has **177 passing backend tests**, including the original 12 compiler tests and 36 geometry/inspector tests. The fixture command creates an original synthetic 640 × 480 workbench image, invokes the normal mock segmentation boundary, prints a `MOCK` summary, and optionally saves the annotated image at the requested path. Expect `found_counts` of one yellow plate and four black pins, `counts_match: true`, `rules_hold: true`, `uncertain: false`, and `deterministic_checks_pass: true`. This last field means deterministic evidence is consistent; it is not a judge verdict or an unlocked step. The segmentation fixture does not analyze the image's contents.

The inspector follows these rules:

- Call SAM for the anchor first and reuse that result. No anchor, multiple distinct anchors, or an unreliable anchor stops inspection with uncertainty; unchecked counts remain unknown, rather than claiming the remaining parts are absent.
- Gate parts by whether their centroid is inside the anchor box. An `outside` rule targeting the anchor permits outside candidates as well; inside candidates are retained so misplaced parts can be reported. An `outside` rule targeting a different part does not disable assembly-zone gating.
- Use full-frame PNG foreground pixels for area, centroid, bounding box, and overlap when available. Grayscale foreground is above 127; an RGBA cutout uses alpha above 127 when transparency is present. Without a mask, use the supplied pixel box. A future real SAM adapter must normalize the officially documented output to this internal contract.
- Drop detections smaller than 16 pixels of area. Suppress near-duplicates at IoU ≥ 0.85, keeping the highest-score instance. Compare actual foreground masks when both are present; otherwise use box IoU. Retained overlap at IoU ≥ 0.5, conflicting labels, invalid detections, or a retained score below 0.70 marks uncertainty. These thresholds are development defaults, not calibrated performance claims; change them with `InspectorConfig`.
- `inside` requires full box containment; `outside` requires disjoint boxes (touching edges are permitted). `left_of` and `above` compare centroids strictly. Quadrants use the target box midpoint and require the part centroid inside the target. A centroid exactly on a dividing axis satisfies no quadrant. Every source instance must satisfy a rule relative to at least one target instance.
- Return separate count/rule results, filtering statistics, detections, issues, and an annotated PNG. Uncertain evidence uses amber boxes, even if counts also disagree. Known misplaced/extra detections use red; other detections use green. Missing parts have no fabricated position or box.

Tests cover missing/low-score/multiple anchors, background parts, missing/extra pins, edge-crossing parts, direction and quadrant rules, explicit outside rules, duplicate and sparse PNG masks, mask centroids, ambiguous overlaps, invalid input, and real-mode rejection. All fixtures and image patterns were authored for this project.

The M3 Python inspection module now feeds the M4 `/verify-step` flow. Thresholds, boxes, and simple spatial rules do not prove that a physical part is correctly fastened or assembled.

## Verify M4: judge, session state, and overrides

Run the complete backend suite and the server-free HTTP workflow check:

```sh
.venv/bin/python -m unittest discover -s backend/tests -v
.venv/bin/python -m scripts.check_workflow
```

The workflow command sends an original synthetic PDF and a generated image through FastAPI in process. It uses the normal mock adapters and writes a real audit snapshot to `sessions/<id>.json`. Expect `mode: "MOCK"`, `verdict: "unsure"`, `next_step_unlocked: false`, step 1 `UNSURE`, and step 2 `LOCKED`. Attempting step 2 returns **409**. The default mock judge intentionally remains unsure, even when fixture counts match; it cannot verify an assembly.

To also exercise the explicit manual override:

```sh
.venv/bin/python -m scripts.check_workflow --exercise-override
```

Expect step 1 `PASSED` with `passed_via: "override"`, its `last_verdict` still `"unsure"`, and step 2 `ACTIVE`. The logged reason explicitly identifies this as a development override, not a model pass. The script prints the audit file path. Its session lives only in the script's process, so use the saved JSON for inspection; that ID will not exist in a separately running backend.

For the interactive HTTP flow, start the backend and open **http://127.0.0.1:8000/docs**:

1. Upload a PDF through `POST /compile-manual`. The existing `{product, steps}` body is preserved; copy the new **`X-StepGuard-Session-ID`** response header. Each successful compilation creates a new session.
2. Call `GET /session/{session_id}`. Expect the checklist, mode, per-step state, audit log, and `reviewed_at: null`, with only step 1 `ACTIVE`. After reviewing every extracted requirement against the manual, call `POST /session/{session_id}/review` (no request body). It saves an idempotent acknowledgment and returns the session. Checks and overrides return **409** until review is saved. A failed save leaves the review gate closed.
3. Call `POST /verify-step` with `{session_id, step_id, image_base64}`. `image_base64` must be raw base64 of a decodable image, without a data URL. Images are limited to 10 MiB decoded and 12 million pixels. For the existing synthetic segmentation fixture, use a 640 × 480 image. In mock mode its contents are not analyzed.
4. The response includes the build prompt's verdict, confidence, counts, issues, masks, latency, and next-step flag, plus a top-level **`message`** for display and speech. With the default mock fixture, expect `unsure`, the low-confidence message, and the next step still locked.
5. Call `POST /override` with `{session_id, step_id, reason}` only when explicitly exercising the manual override. A nonblank reason of at most 1000 characters is required. It passes the current idle step as an override, records the reason/time and previous verdict, and activates its successor. It cannot skip locked steps, alter a passed step, or interrupt a check.
6. Fetch the session again or inspect `sessions/<id>.json` to verify the state and override provenance.

A base64 frame can be prepared locally without printing its contents:

```sh
.venv/bin/python - <<'PY'
import base64
import json
from pathlib import Path
payload = {
    "session_id": "REPLACE_WITH_SESSION_ID_FROM_COMPILE_RESPONSE",
    "step_id": 1,
    "image_base64": base64.b64encode(Path("private_assets/m3-inspection.png").read_bytes()).decode(),
}
Path("private_assets/verify-request.json").write_text(json.dumps(payload))
PY
curl -i http://127.0.0.1:8000/verify-step \
  -H 'Content-Type: application/json' \
  --data-binary @private_assets/verify-request.json
```

Replace the placeholder ID in the Python snippet with the compile response's ID before running it. The PNG can be generated with the M3 fixture command above. The generated request remains in the gitignored private-assets directory.

The judge guard enforces these rules:

- Counts must match, geometry must hold, and issues must be empty for a pass. A model pass cannot override a deterministic count or geometry failure. Counts are also compared directly, independently of the inspector's summary flags.
- Missing/ambiguous anchors, uncertain inspection, malformed judge output, a judge `unsure`, or low model/detection scores produce `unsure`. Unreliable inspection skips the judge call. The score threshold is 0.70; it is a development heuristic, not a calibrated probability or accuracy claim.
- The model may downgrade a deterministic failure to `unsure`. A high-confidence failure needs a stated issue. Fix hints use deterministic evidence when the model contradicts count or geometry failures.
- Missing-part messages do not invent a position. Misplacement directions come from the explicit spatial rule. The browser UI must give the overall `unsure` verdict precedence over per-mask `ok`/`bad` values and show amber feedback; the mask contract has no separate unsure status.

Sessions follow `LOCKED → ACTIVE → CHECKING → PASSED | FAILED | UNSURE`. Retrying a failed/unsure step reactivates it before checking. Only a pass or an explicitly logged override activates the immediate successor. Passing the final step sets `complete: true` and leaves `next_step_unlocked: false` because no next step exists. Conflicting checks, passed-step rechecks, and attempts to check locked steps return **409**; unknown sessions/steps return **404**.

Transitions are serialized in one backend process. Audits use atomic JSON replacement and omit uploaded PDFs, camera frames, masks, API keys, and raw rejected model output. Only checklist/session data, check summaries, UTC times, and override reasons are persisted. Input or adapter failures return the current step to `ACTIVE` for retry without unlocking anything. Audit-write failures return **503** and cannot commit a pass or override. If storage also fails during error recovery, the safe recovery state is retained in memory until a later successful write.

State is in memory: restarting the backend (including a Uvicorn reload) discards live sessions. Existing audit files remain as evidence and are not reloaded as sessions. Run one backend worker. Supervisor overrides are an explicit local-prototype action; there is no user authentication or supervisor identity verification in this scope.

The M4 portion of the suite covers judgment guards, malformed responses, three-step progression, failure/unsure retries, concurrent attempts, logged overrides, stale check tokens, disk-write failures, and sensitive-input omission. Pass/fail model outputs are injected within tests only; the shipped default mock judge remains the authored unsure fixture.

## Verify M5: camera workspace, overlays, and spoken feedback

Start both servers with the commands above, then open **http://127.0.0.1:5173** in a modern browser. Use localhost or HTTPS for camera permissions. These interactive checks require a local browser and webcam:

1. Confirm **MOCK** is visible, the camera is off, and **Check step** is disabled. Select **Choose PDF** and upload a PDF you have permission to use. Expect the two-step development review: instructions, counts, anchors, and relations. **Start inspection** stays disabled until you acknowledge reviewing every step. Start inspection to save the acknowledgment before camera controls appear. The mock compiler ignores the document contents.
2. Select **Enable camera** and grant camera permission. Position the workbench in view. Select **Check step 1**. During the request, controls prevent duplicate actions. A new, unmirrored **640 × 480 JPEG** is captured with letterboxing to preserve the source aspect ratio.
3. Expect an **amber unsure** result, an amber overlay/banner, a message and fix hint, check latency, and step 2 still locked. The normal mock judge always returns unsure; matching fixture counts do not establish a pass. Speech uses the browser's built-in `SpeechSynthesis`, not a Meta model, and may depend on browser/OS settings.
4. Move something in view: the displayed checked frame and its overlays remain frozen together. **Return to live view** (or **Clear captured frame** with the camera off) clears failed/unsure evidence while retaining the server audit log. Then recheck a fresh frame. A pass or override instead holds the checked instruction and evidence until **Continue to next step** or **Finish inspection**; Continue never changes server state.
5. Use **Mute spoken feedback**, then check again. Expect written feedback without speech. Unmute for later checks. **Refresh session** updates state and audit events without repeating speech. A failed refresh disables further checks/overrides until session refresh and, if necessary, backend reconnection succeed.
6. To exercise the explicit development override, expand **Manual override**. A nonblank reason is required. Record a reason such as “Development test: manually inspected the fixture step.” Expect an amber **Manually overridden** label and a reason in the audit log. Step 2 is unlocked on the server, while the workspace keeps step 1 visible until **Continue to next step**. This is a manual action, not an automatic/model pass. The original check frame retains its original step label. The API does not authenticate supervisor identity in this local prototype.
7. Check step 2 and expect unsure again. Optionally record a second explicit development override to verify the completed checklist and disabled check control. Inspect `sessions/<id>.json`: override provenance and reasons remain present; camera frames/masks are omitted.
8. Select **Stop camera** and confirm the browser's camera indicator turns off. Deny permission on a fresh attempt to verify the actionable camera error. Try a narrow browser viewport and keyboard navigation. Restarting the backend expires live sessions; refresh then upload the manual again.

Green pass and red fail presentations are implemented and exercised with injected responses in tests. There is no UI control for manufacturing a verdict. Missing parts receive dashed yellow regions only when a quadrant rule or supported quadrant location plus a detected target establishes the region; a generic “assembly area” hint does not invent a box. Unsure always takes precedence and uses amber, even if individual mask statuses are ok/bad. Failed mask decoding falls back to boxes and a notice.

Run frontend checks without a server or browser:

```sh
cd frontend
npm test
npm run build
```

The original **25 M5 frontend tests** use Node's built-in test runner, esbuild, and React server rendering. They check frame capture/letterboxing, overlay colors and cancellation, mask fallback/tinting, supported missing regions, speech deduplication/mute, upload/API validation and identity checks, and component states for locks, feedback, overrides, and audit text. Browser globals are test doubles: these checks do not verify webcam permissions, playback, actual speech audio, client event handling, or visual layout in a real browser.

## Verify M6: motion-stop and recorded voice triggers

The **Check step** button remains available whenever the camera and current step are ready and no other action is running, including in browsers that do not support recording. No microphone permission is requested until you hold the voice button. Automatic motion checks are off initially and do not start the camera.

For the motion trigger, start both servers, upload a PDF, and enable the camera:

1. Select **Check when motion stops**. A stationary scene should not produce an initial check. Move your hand or an object through the camera view for a moment, then leave the scene still. After about **0.7 seconds** of sustained stillness, expect one captured frame and one `/verify-step` request.
2. The default mock result is **amber unsure**, with the next step locked. Leave the result displayed and move around: no additional automatic check should occur. Select **Resume live view** to rearm; a fresh movement/stillness cycle is required. There is also a **2-second cooldown** after an automatic trigger.
3. Turn the option off and verify movement no longer triggers checks. Stop the camera, switch to a background tab, or start another action: monitoring pauses and discards its old movement history. After returning, a fresh movement cycle is required. Button, motion, and voice actions share the same request guard, preventing overlapping checks.

Motion uses a **64 × 48** canvas sampled about every **100 ms**, with mean absolute luminance differences. Two consecutive high-difference samples arm the detector; low differences sustained for 700 ms fire it. Intermediate movement resets the stillness timer. High/low thresholds are development defaults, not calibrated hand detection: lighting changes, camera shake, and a small/distant work area may affect triggering. No model is called for these sampled frames.

For voice, first turn motion monitoring off to make this check easier to observe:

1. With a ready camera/current step, hold **Hold to speak**, allow microphone access, say **“step done”**, **“check step”**, or **“next step”**, then release. If opening the permission prompt ends the hold, grant permission and hold again. Keep holding through recording; a clip shorter than 250 ms is discarded.
2. Expect a `/transcribe` upload, the clearly labeled **MOCK transcript: “step done”**, then a normal current-step check returning unsure. The fixture does not recognize speech: even recorded silence returns that mock phrase. Real Meta transcription remains M10; the Gemini demo supports actual transcription. None of these phrases skips a step or overrides the server lock; **“next step” checks the current step**.
3. Keyboard users can focus the voice button and hold **Space** or **Enter**. **Escape**, pointer cancellation, loss of focus, hiding the tab, stopping the camera, or leaving the page cancels an in-progress recording. Releasing while permission is still pending cancels the request's recording intent; a late stream is stopped immediately. Audio is discarded on cancellation.
4. Hold for more than **5 seconds** to verify automatic recording stop. The microphone tracks stop before transcription starts. Deny microphone access or disconnect the device to verify an actionable message and the button fallback. Unsupported `MediaRecorder`/audio formats also leave the button flow available.

Command matching normalizes case, whitespace, and final `. ! ?` punctuation, then requires a complete match to one of the three phrases. Unrelated text and negations such as “do not check step” do not request verification. Those cases are tested with injected transcripts, since the default mock always says “step done”.

`POST /transcribe` accepts multipart field **`file`**, up to **5 MiB**, with `audio/webm`, `audio/ogg`, `audio/mp4`, or `audio/wav` (codec parameters are accepted and the MIME is normalized before the adapter call). It checks nonempty content, size, media type, and basic container signatures. These checks do not decode audio or prove that a clip is valid or five seconds long. The browser chooses a supported WebM/Opus, Ogg/Opus, or MP4 recording format; real Meta format support must be verified before M10. Responses are `{text, mock_mode}` with mode/no-store headers. Empty text is permitted for silence; malformed adapter output returns **502**, and the unimplemented real adapter returns **503** without a fixture fallback. Audio and transcripts are not saved in session audits. Multipart processing may temporarily spool uploads; files are closed after each request.

Run the complete automated checks and the extended in-process smoke flow:

```sh
.venv/bin/python -m unittest discover -s backend/tests -v
.venv/bin/python -m scripts.check_workflow --exercise-voice --exercise-override
cd frontend
npm test
npm run build
```

The current suite, including M7 harness preparation and the Gemini adapter, has **177 backend tests** and **73 frontend tests**. The M6 production build passed TypeScript/Vite checks. The smoke flow transcribes original synthetic silence, confirms transcription alone does not change session state, performs the usual unsure check, verifies the next step returns **409**, then records a clearly identified manual override. Its output includes the labeled transcription and the audit path. It is a development transport/state check, not evidence of speech recognition or real assembly inspection.

The 28 new frontend tests cover motion timing, reset/cooldown, hidden-tab sampling, one-shot monitor cleanup, exact commands, microphone permission/release races, five-second stop, recording errors/cancellation/size limits, audio API validation, and control rendering. The 10 new backend tests cover audio transport, adapter output/errors, mode labeling, upload cleanup, and absence of session/audit changes. Browser media/timers are test doubles; actual camera/microphone permissions, pointer/keyboard events, audio encoding, speech playback, and visual layout still need the local walkthrough.

The original Meta integration milestones remain at M6 as described in [the build prompt](STEPGUARD_COMPLETE_PROMPT.md). The user separately authorized Gemini as a temporary demo provider; this addition does not complete the Meta milestones. **M7 starts Phase B and still needs a real SAM adapter and an overhead photo of five distinct parts.** Official base URL/auth, model names, PDF/image/audio contracts, and SAM grammar have now been reviewed and linked in [the readiness review](docs/HACKATHON_READINESS.md). The official Python mask-parser package could not be obtained in this restricted environment; mask decoding will not be guessed.

## M7 preparation: five-phrase SAM check

`scripts/day1_sam_test.py` calls only `backend.meta_client.segment()` and validates the project's internal boxes/scores/full-frame PNG masks with the same helpers as the inspector. It requires exactly five distinct nonblank phrases and a decodable image within the existing 10 MiB/12-million-pixel limits. Each phrase reports `found`, detection count, reliable detection count, mask count, and every detection score. A phrase is found when at least one valid detection meets the existing prototype score threshold of **0.70** and area threshold of **16 pixels**; a box-only detection may count as found, with mask count zero. These thresholds are not calibrated accuracy claims.

A completed real run reports **go** for at least four of five found phrases, or **no_go** for fewer. A no-go means stop and review/change the physical parts as required by the build prompt. Visually compare model findings with the photo: the automated threshold cannot establish that a predicted label is correct. Invalid responses, malformed masks, failed calls, and an unavailable adapter produce an error without a go/no-go decision. Exit codes are **0** for go or an explicitly labeled mock exercise, **1** for a real no-go, and **2** for input/configuration/adapter/output errors. The harness calls only the stable `backend/meta_client.py` boundary; the script contains no guessed provider request format. Real mode requires `MODEL_PROVIDER=meta` and explicitly rejects Gemini.

After the official SAM adapter is implemented and a photo of five actual parts is available, a real run will use this form. Replace the photo and phrases with the actual kit; keep credentials in `.env` and do not paste or print the API key:

```sh
MOCK_MODE=false MODEL_PROVIDER=meta .venv/bin/python -m scripts.day1_sam_test \
  --image private_assets/overhead-five-parts.jpg \
  --phrase 'yellow plate' --phrase 'black pin' --phrase 'silver screw' \
  --phrase 'red beam' --phrase 'black wheel' \
  --report private_assets/m7-sam-real.json
```

**This real command is not ready yet.** The adapter still raises an unavailable error until the documented SAM integration and mask normalization are implemented and tested. A real five-part image and the five corresponding phrases are also needed; the existing M3 image is synthetic.

To exercise only the harness with the authored M3 image:

```sh
.venv/bin/python -m scripts.inspect_fixture --output private_assets/m3-inspection.png
.venv/bin/python -m scripts.day1_sam_test \
  --image private_assets/m3-inspection.png --allow-mock \
  --phrase 'yellow plate' --phrase 'black pin' --phrase 'silver screw' \
  --phrase 'red beam' --phrase 'black wheel' \
  --report private_assets/m7-sam-harness-mock.json
```

Expect **MOCK**, two fixture phrases found, zero masks, and **`decision: "not_evaluated_mock"`**. No image is analyzed in this exercise. Mock mode requires explicit `--allow-mock`; even fixtures with five found phrases never produce a go decision. Reports omit image/mask payloads and cannot overwrite the source photo or a symlink to it.

The 14 harness tests use original synthetic pixels and injected adapter responses to cover the four-of-five gate, mock separation, phrase/image validation, mask normalization, unreliable detections, sanitized adapter errors, fixture rejection in real mode, CLI exit codes, and report handling. The full backend suite now has **166 passing tests**, including the later Gemini tests. These tests and the mock command do not complete M7 or establish real SAM performance.

## Model responsibilities and configuration

`backend/meta_client.py` owns provider selection, mock precedence, and the stable four-function boundary. The temporary REST implementation is isolated in `backend/gemini_client.py` and uses existing dependencies; no SDK or package was added.

- `compile_manual(pdf_bytes)`: Gemini reads the PDF and produces a strictly validated checklist. The future Meta role is Muse Wonder. Mock mode returns the authored checklist fixture.
- `segment(image_bytes, prompt)`: Gemini detects matching objects and normalizes boxes from `[ymin, xmin, ymax, xmax]` in 0–1000 coordinates to image pixels. It returns no segmentation masks. The future Meta role is SAM 3.1. Mock mode returns synthetic boxes.
- `judge(step, found, geometry, annotated_image)`: Gemini returns structured verdict evidence; the existing judge guard enforces deterministic count and geometry failures. The future Meta role is Muse Spark. Mock mode remains unsure.
- `transcribe(audio_bytes, mime)`: Gemini transcribes recorded audio, including empty text for silence. Browser MP4 recordings are submitted as `audio/m4a`. The future Meta role is Muse Voice Transcribe. Mock mode returns `step done`.

The [official Meta overview](https://dev.meta.ai/docs/overview) and endpoint documentation have now been reviewed. Documented identifiers are `muse-wonder-1.0`, `muse-spark-1.3`, `sam-3.1`, and `muse-voice-transcribe-1.0`; the base is `https://api.meta.ai/v1` with bearer authentication. The adapters are still unimplemented and real Meta calls raise `NotImplementedError`; the UI shows **META · NOT READY**. See [remaining integration details](docs/HACKATHON_READINESS.md). Meta Voice requires supported PCM WAV. Local browser conversion to mono 16-bit PCM at 16 kHz is implemented; live Meta transcription validation is still pending. The optional open-weights identifier was confirmed in the participant guide but has not been integrated or run.

Browser `SpeechSynthesis` provides spoken feedback with a mute toggle and once-per-result delivery. Step locking and motion detection run in application code regardless of the model provider. The Gemini demo does not count as completion of M7–M11 or real-kit acceptance testing.

## Repository and private data

- `backend/main.py`: FastAPI application with `/health`, `/compile-manual`, `/verify-step`, `/transcribe`, `/session/{id}`, `/session/{id}/review`, and `/override`.
- `backend/schemas.py`: strict checklist, step, and spatial-rule contracts with cross-field validation.
- `backend/compiler.py`: model-boundary invocation and validated checklist compilation.
- `backend/tests/`: compiler, inspector, judge, state, transcription, and HTTP workflow tests using standard-library `unittest`.
- `backend/judge.py`: validated model output, deterministic verdict guards, messages, and fix hints.
- `backend/state.py`: in-memory sessions, ordered step transitions, and atomic audit snapshots.
- `scripts/check_workflow.py`: repeatable mock HTTP workflow check, including optional synthetic voice transport and a logged override.
- `backend/inspector.py`: anchor-first part inspection, geometry evidence, and image annotation.
- `scripts/inspect_fixture.py`: repeatable mock inspector check using an original synthetic scene.
- `scripts/day1_sam_test.py`: five-phrase SAM boundary check, with explicit mock separation and JSON reporting; the real M7 run is pending.
- `backend/meta_client.py`: four stable model functions, mock fixtures, provider routing, and environment configuration.
- `backend/gemini_client.py`: temporary Gemini REST adapter for PDF, detection boxes, judgment, and audio.
- `backend/model_errors.py`: sanitized provider errors and HTTP status mapping.
- `backend/fixtures/`: project-authored synthetic development data; no third-party manual or image.
- `backend/requirements.txt`: direct dependencies; `requirements.lock` records the complete tested backend environment.
- `frontend/src/`: camera, captured-frame canvas overlays, server checklist, feedback, speech, manual override, audit log, motion monitoring, hold-to-record voice controls, and responsive dark styles.
- `frontend/tests/`: server-free frontend helper, API, motion/recording lifecycle, and component rendering tests; `npm test` uses esbuild and the built-in Node test runner.
- `frontend/package-lock.json`: resolved frontend dependency versions. Rollup and PostCSS are pinned with npm overrides for reproducible installation from the available cache.
- `private_assets/`: gitignored location for private manuals, images, and audio. Only an empty placeholder belongs in version control.
- `sessions/`: gitignored JSON audit snapshots for compiled sessions; they do not restore live state after a restart.

Keep API keys exclusively in `.env` or server environment variables. The frontend never receives the key, endpoint, or model configuration. `.env`, virtual environments, dependencies, build output, private assets, and session data are excluded by `.gitignore`.

Git initialization and commits could not be performed in the agent environment because it denies creating `.git`. Run this locally to create the first milestone commit:

```sh
git init
git add .
git commit -m "Build StepGuard mock workflow with guarded verdicts and audited step locks"
```

No GitHub repository has been created or published.

## Built during the hackathon

Project implementation began on **October 27, 2026**. The starting workspace contained only the build prompt. The M1–M6 application source, M7 test-harness preparation, tests, and synthetic fixtures were written during the event using Codex as the coding assistant. Standard third-party FastAPI, React, Vite, TypeScript, and Tailwind tooling provides the framework and build infrastructure. No pre-existing project application code or third-party manual assets were imported.

## Limitations

This is an unfinished prototype. M6 adds motion and recorded voice triggers to the camera workspace, mock inspection, guarded judgment, session state, and audit logs. In mock mode, PDF uploads return a validated fixture checklist and transcription ignores the recorded speech. In Gemini demo mode, actual inputs reach the REST adapter, but live access, model compatibility, kit accuracy, latency, and quota use have not been verified. The Meta adapters remain pending. Motion thresholds are uncalibrated and do not establish that hands have left the table. The fixed synthetic segmentation fixture is independent of camera contents. It has not been tested on an assembly kit, and there are no accuracy, performance, compliance, or production-readiness claims. The product performs automatic step checking, with no continuous per-frame model calls. Sessions exist only in memory in one backend process; audits do not restore them after a restart. Unsupported or restricted browser speech leaves written feedback available.

M1 verification in the agent environment passed in-process ASGI health/OpenAPI checks, all four fixture calls, mutable-fixture isolation, real-mode rejection of unimplemented adapters, dependency consistency (`pip check`), TypeScript checking, and the Vite production build. At M1, before the separately authorized Gemini addition, a scan found no other AI provider references. M6 passed the full 112-test backend suite, including compiler, inspector, judge, state, transcription, and HTTP workflow checks. The mock fixture command produced the expected counts and an annotated PNG. The in-process workflow check confirmed an unsure verdict, a blocked next step, and a separately logged development override. M6 also passed 53 frontend tests and the TypeScript/Vite production build; the extended smoke flow confirmed that transcription alone does not advance a session. Localhost server binding is denied in that environment; an isolated headless Chrome launch exited before opening a page. Interactive camera/microphone, motion calibration, audio encoding, speech, client event handling, and desktop/mobile visual verification must therefore be performed locally with the steps above. At that earlier checkpoint Git initialization and the first commit were pending. See the current verification record for the latest packaging status.

The Gemini adapter has tests covering intercepted REST requests, header authentication, sanitized failures, structured output, PDF prompts, detection coordinates, audio, mock precedence, provider provenance, and the complete compile/check/session flow. The current complete suite passes 177 backend tests and 73 frontend tests, plus the TypeScript/Vite production build. Reliability and evaluation tests cover bounded retries, validation repair, cache isolation/expiry, check limits, honest failure accounting, and identical baseline/pipeline image pixels. HTTP interception verifies application behavior but cannot establish that a real key/model accepts the payloads. A minimal live connectivity request was attempted, but this environment could not reach Gemini; key validity, model availability, and quota are unconfirmed. This network failure is not evidence that the provided key is wrong. The saved key has been moved into `.env` and cleared from `.env.example`.

## Third-party libraries and licenses

The inventory below includes direct and transitive packages in the backend lock and frontend lock. Package license metadata identifies the license; bundled components may include additional notices in the installed distribution's license files. In particular, NumPy/Pillow wheels and build binaries include their own bundled-component notices. System Python, Node.js, npm, and browser features are local prerequisites, not vendored project libraries. No external fonts, stock images, manuals, or datasets are included.

### Backend (direct and transitive)

- **annotated-doc 0.0.5** — MIT.
- **annotated-types 0.8.0** — MIT.
- **anyio 4.15.1** — MIT.
- **certifi 2026.7.22** — Mozilla Public License 2.0 (MPL 2.0).
- **click 8.5.0** — BSD-3-Clause.
- **fastapi 0.141.1** — MIT.
- **h11 0.16.0** — MIT License.
- **httpcore 1.0.9** — BSD-3-Clause.
- **httpx 0.28.1** — BSD License.
- **idna 3.20** — BSD-3-Clause.
- **numpy 2.5.1** — BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0.
- **pillow 12.3.0** — MIT-CMU.
- **pydantic 2.13.5** — MIT.
- **pydantic_core 2.46.5** — MIT.
- **python-dotenv 1.2.3** — BSD-3-Clause.
- **python-multipart 0.0.32** — Apache-2.0.
- **starlette 1.7.0** — BSD-3-Clause.
- **typing-inspection 0.4.4** — MIT.
- **typing_extensions 4.16.0** — PSF-2.0.
- **uvicorn 0.54.0** — BSD-3-Clause.

### Frontend (direct, transitive, and optional platform packages)

- **@babel/code-frame 7.29.7** — MIT.
- **@babel/compat-data 7.29.7** — MIT.
- **@babel/core 7.29.7** — MIT.
- **@babel/generator 7.29.8** — MIT.
- **@babel/helper-compilation-targets 7.29.7** — MIT.
- **@babel/helper-globals 7.29.7** — MIT.
- **@babel/helper-module-imports 7.29.7** — MIT.
- **@babel/helper-module-transforms 7.29.7** — MIT.
- **@babel/helper-plugin-utils 7.29.7** — MIT.
- **@babel/helper-string-parser 7.29.7** — MIT.
- **@babel/helper-validator-identifier 7.29.7** — MIT.
- **@babel/helper-validator-option 7.29.7** — MIT.
- **@babel/helpers 7.29.7** — MIT.
- **@babel/parser 7.29.8** — MIT.
- **@babel/plugin-transform-react-jsx-self 7.29.7** — MIT.
- **@babel/plugin-transform-react-jsx-source 7.29.7** — MIT.
- **@babel/template 7.29.7** — MIT.
- **@babel/traverse 7.29.8** — MIT.
- **@babel/types 7.29.8** — MIT.
- **@esbuild/aix-ppc64 0.25.12** — MIT.
- **@esbuild/android-arm 0.25.12** — MIT.
- **@esbuild/android-arm64 0.25.12** — MIT.
- **@esbuild/android-x64 0.25.12** — MIT.
- **@esbuild/darwin-arm64 0.25.12** — MIT.
- **@esbuild/darwin-x64 0.25.12** — MIT.
- **@esbuild/freebsd-arm64 0.25.12** — MIT.
- **@esbuild/freebsd-x64 0.25.12** — MIT.
- **@esbuild/linux-arm 0.25.12** — MIT.
- **@esbuild/linux-arm64 0.25.12** — MIT.
- **@esbuild/linux-ia32 0.25.12** — MIT.
- **@esbuild/linux-loong64 0.25.12** — MIT.
- **@esbuild/linux-mips64el 0.25.12** — MIT.
- **@esbuild/linux-ppc64 0.25.12** — MIT.
- **@esbuild/linux-riscv64 0.25.12** — MIT.
- **@esbuild/linux-s390x 0.25.12** — MIT.
- **@esbuild/linux-x64 0.25.12** — MIT.
- **@esbuild/netbsd-arm64 0.25.12** — MIT.
- **@esbuild/netbsd-x64 0.25.12** — MIT.
- **@esbuild/openbsd-arm64 0.25.12** — MIT.
- **@esbuild/openbsd-x64 0.25.12** — MIT.
- **@esbuild/openharmony-arm64 0.25.12** — MIT.
- **@esbuild/sunos-x64 0.25.12** — MIT.
- **@esbuild/win32-arm64 0.25.12** — MIT.
- **@esbuild/win32-ia32 0.25.12** — MIT.
- **@esbuild/win32-x64 0.25.12** — MIT.
- **@jridgewell/gen-mapping 0.3.13** — MIT.
- **@jridgewell/remapping 2.3.5** — MIT.
- **@jridgewell/resolve-uri 3.1.2** — MIT.
- **@jridgewell/sourcemap-codec 1.5.5** — MIT.
- **@jridgewell/trace-mapping 0.3.31** — MIT.
- **@napi-rs/lzma-linux-x64-gnu 1.5.1** — MIT.
- **@rolldown/pluginutils 1.0.0-beta.27** — MIT.
- **@rollup/rollup-android-arm-eabi 4.62.4** — MIT.
- **@rollup/rollup-android-arm64 4.62.4** — MIT.
- **@rollup/rollup-darwin-arm64 4.62.4** — MIT.
- **@rollup/rollup-darwin-x64 4.62.4** — MIT.
- **@rollup/rollup-freebsd-arm64 4.62.4** — MIT.
- **@rollup/rollup-freebsd-x64 4.62.4** — MIT.
- **@rollup/rollup-linux-arm-gnueabihf 4.62.4** — MIT.
- **@rollup/rollup-linux-arm-musleabihf 4.62.4** — MIT.
- **@rollup/rollup-linux-arm64-gnu 4.62.4** — MIT.
- **@rollup/rollup-linux-arm64-musl 4.62.4** — MIT.
- **@rollup/rollup-linux-loong64-gnu 4.62.4** — MIT.
- **@rollup/rollup-linux-loong64-musl 4.62.4** — MIT.
- **@rollup/rollup-linux-ppc64-gnu 4.62.4** — MIT.
- **@rollup/rollup-linux-ppc64-musl 4.62.4** — MIT.
- **@rollup/rollup-linux-riscv64-gnu 4.62.4** — MIT.
- **@rollup/rollup-linux-riscv64-musl 4.62.4** — MIT.
- **@rollup/rollup-linux-s390x-gnu 4.62.4** — MIT.
- **@rollup/rollup-linux-x64-gnu 4.62.4** — MIT.
- **@rollup/rollup-linux-x64-musl 4.62.4** — MIT.
- **@rollup/rollup-openbsd-x64 4.62.4** — MIT.
- **@rollup/rollup-openharmony-arm64 4.62.4** — MIT.
- **@rollup/rollup-win32-arm64-msvc 4.62.4** — MIT.
- **@rollup/rollup-win32-ia32-msvc 4.62.4** — MIT.
- **@rollup/rollup-win32-x64-gnu 4.62.4** — MIT.
- **@rollup/rollup-win32-x64-msvc 4.62.4** — MIT.
- **@tailwindcss/node 4.3.3** — MIT.
- **@tailwindcss/oxide 4.3.3** — MIT.
- **@tailwindcss/oxide-android-arm64 4.3.3** — MIT.
- **@tailwindcss/oxide-darwin-arm64 4.3.3** — MIT.
- **@tailwindcss/oxide-darwin-x64 4.3.3** — MIT.
- **@tailwindcss/oxide-freebsd-x64 4.3.3** — MIT.
- **@tailwindcss/oxide-linux-arm-gnueabihf 4.3.3** — MIT.
- **@tailwindcss/oxide-linux-arm64-gnu 4.3.3** — MIT.
- **@tailwindcss/oxide-linux-arm64-musl 4.3.3** — MIT.
- **@tailwindcss/oxide-linux-x64-gnu 4.3.3** — MIT.
- **@tailwindcss/oxide-linux-x64-musl 4.3.3** — MIT.
- **@tailwindcss/oxide-wasm32-wasi 4.3.3** — MIT.
- **@tailwindcss/oxide-win32-arm64-msvc 4.3.3** — MIT.
- **@tailwindcss/oxide-win32-x64-msvc 4.3.3** — MIT.
- **@tailwindcss/vite 4.3.3** — MIT.
- **@types/babel__core 7.20.5** — MIT.
- **@types/babel__generator 7.27.0** — MIT.
- **@types/babel__template 7.4.4** — MIT.
- **@types/babel__traverse 7.28.0** — MIT.
- **@types/estree 1.0.9** — MIT.
- **@types/react 19.2.17** — MIT.
- **@types/react-dom 19.2.3** — MIT.
- **@vitejs/plugin-react 4.7.0** — MIT.
- **baseline-browser-mapping 2.11.14** — Apache-2.0.
- **browserslist 4.28.8** — MIT.
- **caniuse-lite 1.0.30001809** — CC-BY-4.0.
- **convert-source-map 2.0.0** — MIT.
- **csstype 3.2.3** — MIT.
- **debug 4.4.3** — MIT.
- **detect-libc 2.1.2** — Apache-2.0.
- **electron-to-chromium 1.5.408** — ISC.
- **enhanced-resolve 5.24.5** — MIT.
- **esbuild 0.25.12** — MIT.
- **escalade 3.2.0** — MIT.
- **fdir 6.5.0** — MIT.
- **fsevents 2.3.3** — MIT.
- **gensync 1.0.0-beta.2** — MIT.
- **graceful-fs 4.2.11** — ISC.
- **jiti 2.7.0** — MIT.
- **js-tokens 4.0.0** — MIT.
- **jsesc 3.1.0** — MIT.
- **json5 2.2.3** — MIT.
- **lightningcss 1.32.0** — MPL-2.0.
- **lightningcss-android-arm64 1.32.0** — MPL-2.0.
- **lightningcss-darwin-arm64 1.32.0** — MPL-2.0.
- **lightningcss-darwin-x64 1.32.0** — MPL-2.0.
- **lightningcss-freebsd-x64 1.32.0** — MPL-2.0.
- **lightningcss-linux-arm-gnueabihf 1.32.0** — MPL-2.0.
- **lightningcss-linux-arm64-gnu 1.32.0** — MPL-2.0.
- **lightningcss-linux-arm64-musl 1.32.0** — MPL-2.0.
- **lightningcss-linux-x64-gnu 1.32.0** — MPL-2.0.
- **lightningcss-linux-x64-musl 1.32.0** — MPL-2.0.
- **lightningcss-win32-arm64-msvc 1.32.0** — MPL-2.0.
- **lightningcss-win32-x64-msvc 1.32.0** — MPL-2.0.
- **lru-cache 5.1.1** — ISC.
- **magic-string 0.30.21** — MIT.
- **ms 2.1.3** — MIT.
- **nanoid 3.3.20** — MIT.
- **node-releases 2.0.53** — MIT.
- **picocolors 1.1.1** — ISC.
- **picomatch 4.0.7** — MIT.
- **postcss 8.5.26** — MIT.
- **react 19.2.7** — MIT.
- **react-dom 19.2.7** — MIT.
- **react-refresh 0.17.0** — MIT.
- **rollup 4.62.4** — MIT.
- **scheduler 0.27.0** — MIT.
- **semver 6.3.1** — ISC.
- **source-map-js 1.2.2** — BSD-3-Clause.
- **tailwindcss 4.3.3** — MIT.
- **tapable 2.3.3** — MIT.
- **tinyglobby 0.2.17** — MIT.
- **typescript 5.9.3** — Apache-2.0.
- **update-browserslist-db 1.3.1** — MIT.
- **vite 6.4.5** — MIT.
- **yallist 3.1.1** — ISC.
