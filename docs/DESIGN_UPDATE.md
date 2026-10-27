# Workbench design update

Implemented October 27, 2026 in the existing local React/FastAPI application.
This replaces the earlier navy/cobalt sidebar design with the approved Workbench
direction: olive surfaces, copper actions, structural rules, serif work-order
titles and step numbers, and a compact horizontal header. Fonts are local system
fonts; no external assets or new dependencies are needed.

## Operator experience

- A functional procedure-loading sheet with PDF drag-and-drop, sample onboarding,
  and the three-stage Load / Review / Inspect indicator.
- A requirements review sheet with the existing server-saved acknowledgment gate.
- A narrow work order containing product, server progress, nearby steps, actual
  part quantities, reference anchor, and placement rules. Phone layouts show the
  presented step and offer all instructions in a disclosure.
- A large evidence area with opt-in camera controls, the actual captured image,
  frame/step/attempt labels, count summaries, and written overlay descriptions.
  Unknown counts use an em dash, separately from a detected zero. Unsure counts
  remain explicitly unverified.
- Feedback and a single primary check/retry/Continue action beneath the evidence.
  Results scroll into reach after completion. The checked instruction remains
  presented until Continue, even when the server has unlocked the next step.
- Manual override, motion/voice controls, and audit history remain available in
  subordinate disclosures. Overrides retain their reason and separate provenance.
- A native workflow dialog, visible keyboard focus, reduced-motion support, and
  the existing report/download and recovery paths.

There is no illustration posing as a camera feed. Mock mode remains explicit:
manuals, frames, and speech are not analyzed, and automatic checks return unsure.
Real Meta adapters, model accuracy, physical-kit checks, and real device testing
remain pending.

## Verification

- `python3 scripts/project.py check`: 177 backend and 76 frontend tests passed
  (253 total), dependency check, TypeScript/production build, fixture typecheck,
  built release smoke flow, and source allowlist passed.
- Added regression coverage for unknown versus zero counts, avoiding duplicate
  camera check actions, and distinguishing a held step from the unlocked next step.
- Actual built application: sample onboarding, fixture acknowledgment, recorded
  test-only override, held instruction, and Continue to step 2 verified in browser.
  No physical assembly or live model result was claimed.
- Nine synthetic states checked at 1280, 768, 390, and 320 CSS px, both ordinary
  and 50-step/long-instruction procedures. No horizontal document overflow.
- Desktop and phone layouts visually inspected; browser console had no errors.
  Screenshots and layout logs are stored in ignored
  `private_assets/workbench-verification/`. Synthetic fixtures are development-only
  and excluded from the production entry.

Run the existing release with `python3 scripts/project.py run --build --port 8001`.
The local preview is at http://127.0.0.1:8001/.
