# StepGuard hackathon readiness

Reviewed October 27, 2026. **Not submission-ready.** The local prototype and Gemini demo adapter are implemented. Actual Meta runtime usage, physical-kit evidence, repository publication, and video submission are outstanding.

## Official sources and deadline

- [Participant guide](https://cerebralvalley.ai/e/meta-ai-developer-hackathon/details): project rules, public repositories, submission format, judging, credits, and dates. The full guide was read in the browser.
- [Official rules/waiver](https://cerebralvalley.ai/e/meta-ai-developer-hackathon/waiver): eligibility, entry, intellectual property, and legal conditions. The full rules were read in the browser; no terms were accepted on the user's behalf.
- [Meta event page](https://dev.meta.ai/events/global-hackathon): official event overview.

Submission closes **November 4, 2026, 9:00 PM US Eastern Standard Time**, corresponding to **November 5, 2026, 7:30 AM India Standard Time**. The project's earlier November 3 target leaves time for submission problems.

## Mandatory requirements

- **Theme fit: supported by the concept.** Manual-driven assembly checking fits the manufacturing theme. Final interpretation belongs to the organizers/judges.
- **Meta model use: not met.** The guide requires incorporating Meta models, and first-stage screening checks meaningful Meta API and/or Meta open-weight usage. The current live provider is Gemini; Meta adapters still reject real calls. Writing code with Codex does not satisfy runtime Meta usage. No blanket prohibition on auxiliary providers was found in the rules reviewed, but Gemini alone cannot meet this requirement. The original project plan has a stricter Meta-only final-runtime goal; the user authorized Gemini temporarily for development.
- **Public repository: not met.** This workspace has no Git repository, commits, or public project URL. Initialization was blocked by the agent environment's filesystem restrictions. Create real commits and publish the source; do not manufacture or backdate history. Exclude `.env`, private manuals/photos, sessions, build output, and dependencies.
- **Three-minute video: not met.** No recorded, accessible video has been supplied. Use the demo plan in `DEMO_SCRIPT.md` after real runs work. Show the actual provider, failures, correction, and locked-step behavior. Verify access to every submitted link while signed out.
- **Accessible working product and code: partly met.** Source, setup instructions, tests, and a frontend build exist. A working app must be demonstrable to judges. Local execution plus video is the project baseline; this review did not find a separate mandatory cloud-deployment requirement. No hosted product is configured. Localhost startup from this agent session was denied on both ports; run the documented commands in a normal local terminal.
- **New work during the event: stated, evidence incomplete.** The workspace history states implementation began October 27 from the build prompt. There is no Git history to independently support that statement. Identify event-period contributions clearly and show only eligible work in the demo.
- **Team/entry information: user action needed.** Solo entry is allowed; teams have at most four people. The representative must submit in the selected track and identify all collaborators. Registration acceptance, eligibility, waiver acceptance, and final submission have not been verified from this workspace.
- **Asset rights and licenses: partly met.** Private assets and secrets are ignored, synthetic fixtures are labeled, and dependency licenses are listed in the README. The user must verify rights to the actual manual, kit photos, video/audio, and any submitted assets. No third-party manual is bundled.
- **Policy and originality requirements: final user review needed.** The rules include content restrictions and rights obligations. StepGuard's stated assembly workflow does not suggest a prohibited use; repository inspection cannot certify every legal/eligibility condition.

The guide identifies simple image analyzers as unsuitable examples. StepGuard should demonstrate the complete manual → visual primitives → localized detections → count/spatial checks → guarded verdict → step lock → correction → audit workflow. This makes the intended technical depth clear; it does not guarantee organizer approval.

## Project acceptance gates beyond the event rules

- **M1–M6:** local application flow, deterministic inspection, conservative judge, step locks, reason-required overrides, camera overlays, speech, motion and recorded-voice triggers implemented and tested with fixtures/injected providers.
- **Temporary Gemini demo:** PDF, detection boxes, judgment, and transcription adapters implemented. Key now resides in `.env` with live Gemini selected; `.env.example` is clear. One connectivity request failed because the environment could not reach Gemini. This does not establish that the key is invalid. Live PDF/image/audio access and accuracy remain unverified.
- **M7:** five-phrase SAM harness exists. Real SAM adapter, actual overhead kit photo, mask normalization/decoding, and the four-of-five detection gate remain pending. The official Python `meta-sam-parser` package is documented, but could not be obtained in this restricted environment. Do not replace SAM masks with invented rectangles or claim Gemini boxes are SAM results.
- **M8–M10:** Meta Wonder PDF compiler, Spark judge, and Voice Transcribe adapters plus real-input validation remain pending. Meta Voice accepts mono 16-bit PCM WAV at 16/24 kHz; current browser recordings need conversion before those requests. Gemini transcription already accepts the current browser formats.
- **M11:** physical-kit workflow, correct/missing/wrong-part/wrong-place cases, camera/microphone permissions, voice recognition, and motion calibration remain untested on actual hardware.
- **M12:** bounded timeouts/retries, visible retry feedback, detection cache, check-rate cap, and safe model-call timing logs implemented. Controls are local to one backend process. Real-provider quota and latency behavior remain unmeasured.
- **M13:** comparison runner and input/report safeguards implemented. No physical measurements exist. `eval/results.md` explicitly says not run.
- **M14:** setup, provider disclosures, model roles, limitations, licenses, evaluation instructions, readiness review, and demo plan written. Final cleanup and submission links depend on the outstanding work above.
- **M15:** optional Meta open-weight/Baseten judge is not integrated. It is a bonus path, not required for the main submission. Do not enable `USE_OPEN_WEIGHTS` or claim bonus eligibility from configuration alone.

## Verified official API references for the remaining integration

- [Overview and models](https://dev.meta.ai/docs/overview): `https://api.meta.ai/v1`, bearer authentication, Wonder `muse-wonder-1.0`, Spark `muse-spark-1.3`, SAM `sam-3.1`, Voice `muse-voice-transcribe-1.0`.
- [Responses API](https://dev.meta.ai/docs/protocols/responses), [file handling](https://dev.meta.ai/docs/file-handling), and [structured output](https://dev.meta.ai/docs/structured-output): use inline PDF/image inputs, `store:false`, completed output validation, and the documented JSON format plus local checklist validation.
- [SAM requests](https://dev.meta.ai/docs/sam/segmenting), [output grammar](https://dev.meta.ai/docs/sam/reading-segmentation), and [official parsers](https://dev.meta.ai/docs/sam/client-libraries): one concept per request, confidence requested explicitly, source-pixel inclusive wire boxes, cropped encoded masks. Normalize these to the inspector's half-open boxes and full-frame binary PNG masks. Reject malformed output.
- [Speech to text](https://dev.meta.ai/docs/speech-to-text): multipart `/asr/transcribe`, JSON settings and a supported WAV recording, transcript validation.

## Validation recorded in this workspace

The complete backend suite passes **166 tests** with fixture mode selected explicitly. The frontend suite passes **56 tests**, and TypeScript/Vite production build checks pass. Tests cover transport, state transitions, invalid-output handling, retries, cache isolation, rate limits, and evaluation accounting using authored data or intercepted responses. The provider-check command reports configured live Gemini mode without revealing the key. A source scan found no actual saved secret in publishable source files; `.env.example` has no credentials. No Git history exists to scan. These checks do not establish live provider access or physical assembly performance.

## Judging preparation

The published weights are impact 30%, Meta tooling 25%, technical depth 20%, and demo 25%. Show the practical assembly problem and a complete correction loop. Explain what each actual Meta model contributes once integrated. Include measured failures and uncertainty rather than unsupported accuracy claims. Browser speech, geometry, motion detection, and step locks are ordinary application code and should be described accurately.

Credits must be claimed individually through the official process before the deadline, with any required billing setup handled by the participant. No credit claim, billing change, registration, repository publication, or final entry was submitted by this agent.
