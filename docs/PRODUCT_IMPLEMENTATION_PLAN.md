# StepGuard: hackathon implementation plan

Status: active scope approved by the user on October 27, 2026. This plan replaces the earlier full-product proposal for the current build. It describes planned work, not completed features. Keep the filename stable so existing links continue to work.

## 1. Goal and scope

Deliver a polished, reliable demonstration of automatic assembly step checking on one physical kit using a fixed overhead camera. Keep React/TypeScript and FastAPI, the existing model boundary, deterministic inspection, and server-controlled progression. Continue to describe the release honestly as a prototype.

The central demonstration is:

**Upload manual → review extracted requirements → check assembly → detect a mistake → keep the next step locked → correct the assembly → pass and unlock → show measured evidence.**

Prioritize actual Meta usage, clear operator interactions, physical-kit validation, and an accessible submission. The full-software roadmap is deferred until after the event.

## 2. Official requirements and current blockers

Use [the official participant guide](https://cerebralvalley.ai/e/meta-ai-developer-hackathon/details), [official rules](https://cerebralvalley.ai/e/meta-ai-developer-hackathon/waiver), and [the detailed readiness review](HACKATHON_READINESS.md) as the submission references.

- Actual Meta API and/or Meta open-weight use is required. Gemini alone does not satisfy this requirement. Gemini remains authorized for temporary development and rehearsal, with accurate provider labeling; it must not be presented as Meta evidence. The original plan targets a Meta-only submitted runtime.
- Public repository, three-minute demo video, and an accessible working product/code are required. Local execution and video are the project baseline; cloud deployment is optional unless the organizers specify otherwise.
- Explain the manufacturing use case and demonstrate the integrated workflow. The guide lists simple image analyzers as unsuitable examples; StepGuard must visibly show manual-derived requirements, localized evidence, geometry, guarded judgment, and progression.
- The published judging weights are impact 30%, Meta tooling 25%, demo 25%, and technical depth 20%.
- Target submission: November 3, 2026. Official deadline: November 4 at 9:00 PM EST, corresponding to November 5 at 7:30 AM IST.
- Team eligibility, registration, asset rights, collaborator information, and final submission require participant verification. Do not accept terms or submit entries automatically.

Current blockers remain unchanged by this document: real Meta adapters and access, physical-kit measurements, public repository/history, and the recorded video. Tests with intercepted model responses establish application behavior, not live model performance.

## 3. Included in the hackathon release

1. PDF upload and validated checklist compilation.
2. A lightweight review of the generated instructions, expected counts, anchor, and spatial requirements before inspection starts.
3. A focused operator workspace with current instruction, expected parts, camera, one prominent check action, and nearby feedback.
4. Actual part localization, deterministic count/geometry checks, conservative pass/fail/unsure judgment, and locked progression.
5. Clear captured-frame overlays, written correction hints, and browser speech.
6. Existing button, recorded voice, and motion-stop triggers through the same guarded check flow. Verify optional triggers before demonstrating them.
7. Compact progress navigation and accessible check/override history.
8. Real-photo evaluation, reproducible local setup, honest limitations, public source, and a three-minute demonstration.

Manual overrides remain reason-required and visibly identified. The local prototype does not authenticate a supervisor, so do not claim role enforcement. Never use an override to stand in for an automatic pass in the demo.

## 4. UI issues to fix

These findings come from source inspection and require rendered-browser verification during implementation.

- Setup, camera controls, voice/motion options, checklist, feedback, overrides, and history currently compete on one page.
- Promotional headings and M6 development labels displace the procedure, active step, and next action.
- Many labels are 8–12 px, with small controls and dimmed text that require readability and contrast improvements.
- The current instruction and expected parts are separated from the main check action.
- On narrow screens, the result follows a long camera/control column; the operator may need to scroll to understand the outcome.
- Multiple connection, provider, camera, and error notices can accumulate without a single clear recovery path.
- A long checklist can dominate the sidebar. Details and audit history need progressive disclosure.

Preserve the current strengths: server-owned state, conservative uncertainty, deterministic guards, explicit provider/mock provenance, frame-specific overlays, and regression coverage.

## 5. UI design principles and proposed flow

### Hierarchy and consistency

One primary action per state: upload, review/start, check, retry, or continue. Define a small reusable set of typography, spacing, surface, border, focus, button, input, and status tokens. Use a 4 px spacing base, approximately 16 px body text and 14 px supporting text, larger current instructions, and 44 × 44 CSS px targets for primary touch controls. Verify the actual result rather than treating these defaults as proof of accessibility.

Use a neutral application shell, a dark camera stage, and one restrained action accent. Choose a single readable theme for the hackathon after checking the actual screen and lighting; a theme switcher is deferred. Colors communicate status and never replace words or icons.

### Setup and checklist review

Show upload progress without invented percentages. After compilation, show the extracted requirements for review, with a clear Start inspection action. Review is an acknowledgment that the requirements were checked, not proof of model correctness.

The minimum scope is read-only review and acknowledgment. If extraction is wrong, stop and correct the input/compiler, then recompile; do not silently alter requirements during a running session. A full checklist editor, approval roles, and published versions are deferred. If review acknowledgment gates starting a session, enforce it on the server rather than only hiding the check button. Keep this addition small and covered by workflow tests.

### Focused inspection workspace

- Compact header: product/manual, current step and progress, and useful connection/readiness status. Move milestone labels and technical diagnostics out of the operator's main view. Keep mock/provider disclosures accurate and accessible.
- Main area: prominent current instruction and expected parts, followed by the camera and primary Check step action.
- Result area: beside the camera on desktop and directly after the check area on smaller screens. Keep the latest result and its correction action easy to reach.
- Step navigator: compact progress list; expand instructions on demand instead of giving every step equal visual weight.
- Secondary tools: optional voice/motion controls, inspection details, manual override, and audit history available without dominating the workspace.

Distinguish live video from the captured frame and associate the result with its step and attempt. After pass, keep the checked evidence visible with an explicit Continue action before presenting the next task. The server may already unlock the next step; Continue changes presentation and must not bypass or duplicate server transitions. Motion-triggered checks rearm only when a new active step is presented and live view is ready.

### Feedback and recovery

Use consistent labels: Passed; Needs correction; Unable to verify; Checking; Manually overridden. Include icons/text with color. Distinguish model uncertainty from service/network failure. Do not display uncalibrated confidence as a reliability percentage.

Show one relevant recovery action for camera denial, disconnection, provider failure, quota exhaustion, and stale session state. Explain disabled primary actions near the control. Do not dismiss a meaningful failure merely by hiding its notice.

### Accessibility and responsive behavior

Support keyboard use, visible focus, logical reading order, written audio alternatives, readable contrast, zoom/reflow, and reduced motion. Avoid unnecessary animation and stacked scroll regions. Announce check results without repeatedly reading the entire page. Add text descriptions for overlay findings.

Review at 1280 × 800 desktop, 768 × 1024 tablet, and a 390 px narrow-screen fallback. Check long instructions and a 50-step checklist. These are implementation targets, not a claim of WCAG conformance.

## 6. Implementation order and acceptance gates

### H1 — prove the Meta path on the selected kit

Implement SAM against the official contracts and normalize actual boxes/masks to the inspector contract. Run the existing five-phrase harness on an overhead photo of five distinct parts. At least four of five phrases must be found reliably before proceeding under the original M7 gate. If it fails, adjust the kit, framing, or phrases and retest; never fabricate detections.

Then implement and validate Wonder manual compilation and Spark judgment on correct, missing-part, and wrong-part images. Validate Voice Transcribe with supported PCM WAV conversion and an actual recorded command. Keep all calls behind the existing boundary and preserve bounded retries and sanitized failures.

Acceptance: real requests and normalized outputs are verified; no fixture fallback exists in real mode; provider failures and malformed output cannot pass or unlock a step. Record what actually worked. If credentials are unavailable, progress on H2/H3 using labeled development modes while H1 remains explicitly blocked.

### H2 — specify and implement the focused UI

Create low-fidelity layouts for setup/review and the operator workspace, then implement reusable tokens/components and the revised hierarchy. Extract frontend orchestration only where needed to make the new interaction clear; avoid a framework rewrite or broad architecture migration.

Acceptance: operator can identify the current task, captured evidence, result, and next action without searching through secondary panels. Verify empty, compiling, review, camera-off, ready, checking, retrying, fail, unsure, pass, override, offline, and complete states. Existing server locks and provider disclosures remain correct.

### H3 — lightweight review and interaction hardening

Add the review acknowledgment if selected, server enforcement for its start gate, explicit result acknowledgment/Continue presentation, contextual recovery, and deliberate motion/voice rearming. Preserve existing API contracts where practical; add focused contracts only where the workflow requires them.

Acceptance: checking cannot start before any required review; stale feedback is not presented as a check of the new active step; duplicate triggers cannot overlap checks; Continue cannot unlock a server-locked step; a failed save cannot commit progression. State what browser refresh/backend restart currently loses and provide a clear restart path.

### H4 — validate one real assembly end to end

Use a manual and kit with at least three visually checkable steps and distinct parts. Confirm that the extracted counts and relations actually match the manual. Visually unverifiable requirements, such as torque, require uncertainty or explicit human review rather than an automatic visual pass.

Acceptance: complete three consecutive correct steps, then repeat the full correct run five times under the original project acceptance target. Demonstrate a wrong or missing part with correction feedback and the next step locked; fix it and obtain a genuine pass/unlock. Test wrong placement when the checklist defines that relation, plus an occluded/uncertain case. Record all failures, not only successful rehearsals. If the target is not met, adjust and rerun or disclose the unmet gate.

Test camera/microphone permissions and disconnection, actual voice recognition, browser speech, motion calibration, retries, quota errors, and recovery on the demonstration machine. Optional features that are unreliable must not be presented as verified capabilities.

### H5 — collect evidence and package the entry

Run the existing baseline-versus-pipeline runner on independently labeled correct, missing, wrong-part, wrong-place, and low-confidence photos. Keep errors in the denominator and label the actual provider. Save real outcomes in `eval/results.md`; no fixture measurements count as model evidence.

Finish local setup instructions, limitations, model responsibilities, event-period contributions, asset/license checks, and secret cleanup. Create genuine Git history and publish the repository when permitted. Record the three-minute video using [the demo plan](DEMO_SCRIPT.md); verify repository/video access while signed out. Complete participant-controlled entry steps before the deadline.

Acceptance: actual Meta use is demonstrated; code and video are accessible; the video shows the integrated workflow and real outcomes; all claims match measured behavior. Confirm every item in [the readiness review](HACKATHON_READINESS.md), rather than treating this plan as evidence of completion.

## 7. Tests and completion checklist

Software progress and current verification are recorded in [the offline release status](RELEASE_STATUS.md). Unchecked live/device/submission gates are intentionally not treated as completed software work.

- [ ] Real Meta SAM gate passed on the chosen kit; compiler, judge, and demonstrated voice path verified.
- [x] New UI reviewed in browser at target sizes; instruction, result, and action remain readable/reachable.
- [ ] Keyboard, focus, contrast, zoom, and permissions/recovery checks completed.
- [x] Review/start and Continue behavior preserve server-controlled progression.
- [ ] Correct three-step assembly, repeated full runs, error/correction loop, and uncertain case recorded honestly.
- [x] Backend/frontend regression suites and TypeScript/production build pass after changes.
- [ ] Relevant browser/device tests run; synthetic tests clearly separated from real-device/model evidence.
- [ ] Evaluation contains actual labeled-photo results, errors, false passes, and latency with limitations.
- [ ] Public repository excludes keys, private assets, sessions, dependencies, and generated build output.
- [ ] README and video identify actual models, browser speech, prototype limitations, and event-period work.
- [ ] Public repository and three-minute video links verified; participant entry requirements completed.

## 8. Deferred until after the hackathon

Saved-procedure libraries, publication/version-management systems, database migration, durable job queues, cross-restart session recovery, accounts and authenticated roles, team dashboards, advanced reports, multi-tenancy, billing, integrations, multi-camera support, native apps, and offline inference are outside the current implementation scope.

Session recovery is an optional improvement only after H1–H5 are secure and time remains. The optional Meta open-weight/Baseten path also stays last; it must not delay the core submission. Do not add either merely to make the application appear larger.

After the event, revisit these features using real operator feedback and a separate product plan. A polished hackathon prototype is the current target; production readiness needs its own evidence and release gates.
