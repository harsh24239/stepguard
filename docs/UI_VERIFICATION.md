# Operator workflow verification — October 27, 2026

The focused UI and interaction hardening have been implemented locally. This
record describes application verification only. Meta integration, live model
accuracy, physical-kit runs, and real camera/microphone checks remain pending.

## Implemented

- Separate upload, requirements review, and inspection screens.
- Read-only instructions, counts, anchors, and placement requirements before
  starting. `POST /session/{id}/review` saves an idempotent acknowledgment.
  The backend rejects checks and manual overrides before it is saved.
- Current instruction and expected parts above the camera; one check action;
  feedback beside the camera on desktop and immediately following its panel
  on smaller screens. Narrow-screen results scroll into reach after a check.
- A captured frame is labeled with step and attempt. A pass or manual override
  retains the checked instruction and disables next-step triggers until Continue.
  Continue is presentation only and requires a fresh server-confirmed passed step.
- Frame evidence and old failed results cannot be treated as a check of a new
  active step. Failed/uncertain checks return to live view before retrying.
- Collapsed step instructions/navigation, motion/voice controls, and audit history.
- Written overlay/count descriptions, visible keyboard focus, reduced-motion CSS,
  and a light theme with larger text and 44 px primary control targets.
- Contextual network/stale-session recovery and visible provider/mock provenance.
- Reason-required overrides explicitly disclose the lack of supervisor identity
  authentication. A manual override is never labeled as an automatic pass.

## Checks completed

- **170 backend tests passed.** Added tests verify that unreviewed sessions cannot
  call inspection or override, review is idempotent, and a failed acknowledgment
  save cannot open the start gate. Existing concurrency, lock, and failed-save
  regression checks still pass.
- **65 frontend tests passed.** Added review response validation and workflow
  tests cover held pass evidence, stale session snapshots, manual acknowledgment,
  final completion, old failed evidence, and the read-only review screen.
- TypeScript and the Vite production build passed. The development visual fixture
  also passed a separate TypeScript check.
- The in-process mock workflow script passed with synthetic images and audio:
  review saved, default check unsure, next step rejected with 409, transcription
  did not progress the session, and an explicit test override preserved provenance.
- In the rendered browser, uploaded an original synthetic PDF to the actual
  mock backend, confirmed Start was disabled before acknowledgment, started
  inspection, recorded a clearly labeled test-only override, and confirmed the
  instruction stayed on step 1 until Continue. Continue presented step 2 and
  moved keyboard focus to the new instruction.
- Stopped/restarted the local backend: the UI showed offline/Reconnect, disabled
  model actions, reconnected, then handled the expired session with an upload
  recovery path. The local preview was restored in mock mode afterward.
- Checked **27 synthetic responsive scenarios**: review, camera-off, checking,
  retrying, failure, uncertainty, pass, override, and complete at 1280 × 800,
  768 × 1024, and 390 × 844, with long instructions and 50 steps. All had no
  horizontal document overflow; feedback labels and primary actions matched the
  state. Representative desktop/tablet/narrow layouts were visually inspected.
  These fixtures use authored UI responses and an illustration, not model calls.

Local screenshots and the responsive check log are in the ignored
`private_assets/ui-verification/` folder. The development-only visual fixture is
at `/tests/preview.html` when Vite is running; it is excluded from the production
bundle entry. It never calls the model API.

## Still requires hands-on/live verification

- Real camera/microphone permissions, denial/reconnect behavior, recording formats,
  voice recognition, motion calibration, and audible browser speech on the demo
  machine. Unit tests do not establish real-device behavior.
- Actual browser zoom, assistive-technology announcements, device lighting, and a
  fuller contrast/accessibility review. This is not a WCAG conformance claim.
- Live provider quota/timeout behavior. Error contracts are exercised through
  tests; this record does not claim real provider outages were reproduced.
- The live Meta SAM/compiler/judge/transcription gates, real three-step assembly
  repeated five times, labeled-photo measurements, and the real demo recording.
- Public repository destination/publication, asset/license verification,
  collaborator details, and participant-controlled submission.

## Packaging

`scripts/package_source.py` validates a source allowlist and builds a local zip
plus SHA256 file. It excludes credentials, private assets, session audits,
dependencies, bytecode, Git metadata, and generated builds. Its basic key-pattern
scan is preparation, not a security audit or a substitute for final source review.
The initial local Git snapshot records the current work at the actual commit
time; no earlier event-period history is manufactured. Repository publication
remains pending.

See `NEXT_DAY_VALIDATION.md` for the next-day execution order.
