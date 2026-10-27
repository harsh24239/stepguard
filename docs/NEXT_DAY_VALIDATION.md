# Next-day validation and submission handoff

Prepared October 27, 2026. This is an execution checklist, not model evidence.
Meta access is expected October 28. Do not change the live-provider flag until
its adapters have been implemented and tested.

## Ready locally

See [offline release status](RELEASE_STATUS.md) for the completed non-provider implementation, single-server runner, sample mode, report export, WAV conversion, CI, and latest test evidence.

- Upload → read-only requirements review → server-saved Start inspection.
- Focused current instruction, expected counts, anchor, spatial requirements,
  camera/check action, and adjacent feedback.
- Captured frame labels include step and attempt. Automatic pass/manual override
  holds its checked instruction until Continue. Continue only changes presentation;
  the server owns every unlock. Motion/voice wait for the new step and live view.
- Readable light theme, keyboard focus, written overlay/count descriptions,
  reduced-motion handling, compact step navigation, and optional controls/history.
- Fixture regression suites, visual-state preview, evaluation runner, demo script,
  and a local source-packaging command are available.

## Prepare the physical kit

- Select one kit and an authorized PDF with at least three visible assembly steps.
  Prefer distinct colors/shapes that remain visible from the overhead camera.
- Check that compiled instructions, counts, anchors, and placement rules match
  the manual. Stop/recompile on extraction errors. Torque/tightness and hidden
  properties need human review or uncertainty.
- Prepare an overhead photo with five distinct part phrases for the SAM gate.
- Label correct, missing, wrong-part, wrong-place, and occluded images before
  running models. See `eval/README.md`. Keep originals under ignored
  `private_assets/evaluation/`; do not publish assets without rights.

## When Meta access arrives

1. Verify official request/response contracts and the available model identifiers;
   implement the four adapters behind `backend/meta_client.py`. Save keys only
   in local `.env`. Preserve bounded retries, sanitized failures, and no fixture
   fallback in real mode.
2. Run `scripts/day1_sam_test.py --help`, then the five-phrase test on the chosen
   photo. Require four of five reliable findings. Adjust the kit/framing/phrases
   and retest if needed. Keep the actual outputs.
3. Validate Wonder on the real PDF and Spark on correct, missing, and wrong-part
   photos. Validate Voice Transcribe with actual recorded audio and supported PCM
   WAV conversion. Never treat a mocked/intercepted response as a successful live call.
4. Set the verified Meta configuration, restart the backend, reconnect, upload
   again, review the extracted checklist, then start inspection. A readiness
   badge confirms configuration only, not key validity or accuracy.
5. Complete at least three consecutive correct steps. Repeat the full correct
   run five times. Record failures as well as passes. Demonstrate a missing/wrong
   part blocking progression, a genuine corrected pass, wrong placement where
   specified, and an occluded case that stays uncertain.
6. Test camera/microphone permission denial, disconnect/reconnect, browser speech,
   actual voice recognition, motion calibration, quota errors, retries, and stale
   sessions on the demo machine. Leave unreliable optional features out of the demo.
7. Run the baseline comparison with independently labeled real photos. Save real
   provider outcomes to `eval/results.md`; include errors, false passes, and latency.

## Regression and visual checks

From the project root:

```sh
MOCK_MODE=true MODEL_PROVIDER=meta MODEL_MAX_RETRIES=0 DETECTION_CACHE_SECONDS=0 .venv/bin/python -m unittest discover -s backend/tests
MOCK_MODE=true MODEL_PROVIDER=meta .venv/bin/python -m scripts.check_workflow --exercise-override --exercise-voice
```

From `frontend/`:

```sh
npm test
npm run build
```

With Vite running, `/tests/preview.html` is a development-only visual fixture
for review, camera-off, checking/retrying, failure, uncertainty, pass, override,
and complete states. It supports long instructions and 50 steps. It does not call
models, exercise real devices, or ship in the production build. Check at
1280 × 800, 768 × 1024, and 390 px. Also verify real browser zoom, keyboard use,
contrast, screen-reader announcements, and actual device permissions. These
checks are not a claim of WCAG conformance.

## Package and publish

```sh
.venv/bin/python -m scripts.package_source --check
.venv/bin/python -m scripts.package_source
```

The default bundle is `private_assets/stepguard-source.zip`, with a SHA256 file.
It includes source/tests/docs/lockfiles and blank `.env.example`; excludes the
real `.env`, private media, session audits, dependencies, bytecode, Git metadata,
and generated builds. The basic key-pattern check does not replace source review.

- Choose the public repository destination and verify code/asset licensing and
  all collaborator information before publishing. Start genuine Git history;
  do not backdate or manufacture contributions.
- Record `docs/DEMO_SCRIPT.md` only after the live kit gates pass. Include review
  and explicit Continue in the recorded flow. Keep the video within three minutes.
- Verify repository and video access while signed out. Local execution/video are
  the baseline; cloud hosting remains optional under the current project plan.
- Participant verifies eligibility/registration, accepts terms, and submits the
  final entry. The plan targets November 3; verify the organizer's live deadline
  before submission.

## Recovery limits

Page refresh loses the current workspace and captured evidence. Backend restart
clears active sessions; JSON audit files remain but are not reloaded as a database.
Upload/review the manual again to restart. Overrides require a reason but do not
verify a supervisor's identity. These prototype limits remain intentionally visible.
