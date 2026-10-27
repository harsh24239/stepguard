# Offline prototype release status

Updated October 27, 2026. The non-provider software for the hackathon prototype
is implemented and locally verified. This does not mean the hackathon entry or
physical assembly validation is complete. Meta adapter implementation/live access
is excluded from this release.

## Completed engineering

- The focused upload, review, inspection, correction, Continue, and completion UI;
  keyboard focus, responsive layouts, readable statuses, reduced motion, and
  written evidence descriptions.
- Server-owned step locks, a persisted review acknowledgment, duplicate-check
  protection, conservative uncertainty, and reason-required manual overrides.
  A failed save cannot commit a pass or override.
- Camera capture/overlays, motion-stop and recorded-voice trigger implementations,
  and browser speech. Device-specific behavior still needs hands-on validation.
- Local recorded-audio conversion to mono 16-bit PCM WAV at 16 kHz, using browser
  decode/downmix/resampling and a guarded button fallback.
- Explicit development/sample onboarding with no PDF or API key; fixture-only
  review text and backend refusal of the sample route in real mode.
- Downloadable JSON evidence with provider/mode, review, counts of recorded
  actions, errors, and audit/override history. Media and configured credentials
  are excluded. It does not claim accuracy or a supervisor's authenticated identity.
- A single-server built release, with frontend assets and `/api` on one origin;
  private source/configuration paths are not served. Localhost is the default.
- Reproducible setup/run/check commands, an offline GitHub Actions workflow,
  dependency checks, local release smoke test, and source bundle validation.
- Evaluation tooling, model responsibilities, limitations, demo recording plan,
  next-day validation order, and dependency license inventory.

## Verified locally

- **177 backend tests and 73 frontend tests passed** (250 total).
- TypeScript, production build, and the development visual fixture's type check passed.
- `python3 scripts/project.py check` passed: dependencies, suites, built release
  routing, sample/review/report smoke flow, and source-package validation.
- The built release at localhost:8001 passed actual browser sample onboarding,
  fixture acknowledgment, manual-override labeling, Continue, and report download.
  The downloaded report was parsed and confirmed to contain one manual override,
  zero automatic passes, explicit fixture provenance, and no mask payloads.
- Actual browser audio decoding/resampling converted authored 24 kHz audio into
  mono 16-bit PCM at 16 kHz (3,244-byte WAV). No microphone or model was used.
- Nine synthetic UI states, long instructions, and 50 steps fit 1280, 768, 390,
  and 320 CSS px: **36 scenarios without horizontal overflow**.
- A limited rendered-text contrast probe caught secondary-text problems, which
  were corrected. This is not an accessibility conformance certification. Real
  browser zoom, assistive technology, device permissions, lighting, and audio
  output remain hands-on checks.

The GitHub workflow runs the same offline check on pushes and pull requests;
its actual run status belongs in the repository's Actions page. A workflow file
or local passing test is not evidence that hosted CI has already run.

Local browser evidence is in ignored `private_assets/release-verification/`.
All authored fixture outcomes are separate from measured model performance.

## Publication approval

The complete source is committed locally. Public upload to
`https://github.com/harsh24239/stepguard` has not been performed: it requires the
user's explicit approval of that destination and public visibility. The CI
workflow is ready, but hosted CI has not run because publication is pending.
The source zip remains available locally regardless of publication.

## Remaining external/live gates

1. Implement and verify the real Meta compiler, SAM localization/masks, judgment,
   and transcription contracts once access is available. A key alone does not
   complete those adapters; real mode has no fixture fallback.
2. Select an authorized physical kit/manual with three visible steps; run the
   correct assembly five times, an error/correction loop, placement failure, and
   an uncertain/occluded case. Test real camera/microphone and optional triggers.
3. Run independently labeled real-photo evaluation and replace `eval/results.md`
   with actual outcomes, errors, false passes, and latency. No values are invented.
4. Record and publish the real three-minute demonstration; verify repository/video
   access while signed out. Cloud hosting is optional under the current plan.
5. Participant verifies assets/licenses, collaborators, eligibility, registration,
   accepts any legal terms personally, and submits the entry.

Accounts, databases, durable job queues, authenticated supervisor roles, and
cross-restart recovery remain outside the approved hackathon scope. Page refresh
starts a new workspace; a backend restart clears in-memory sessions. Audit files
are retained as evidence, not reloaded as a database.

## Commands

```sh
python3 scripts/project.py setup
python3 scripts/project.py check
MOCK_MODE=true MODEL_PROVIDER=meta python3 scripts/project.py run --build
```

Use `--port 8001` if the development backend already uses 8000. Setup preserves
an existing `.env`. Never put keys into source, the frontend, or GitHub Actions.
