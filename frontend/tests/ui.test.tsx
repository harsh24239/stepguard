import test, { afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { renderToStaticMarkup } from 'react-dom/server';
import { captureFrame, colors, containRect, drawOverlay, missingZones, overlayColor } from '../src/lib/overlay';
import { browserSpeech, createSpeaker } from '../src/lib/speech';
import * as api from '../src/lib/api';
import type { Session, VerifyResult } from '../src/lib/types';
import Checklist from '../src/components/Checklist';
import FeedbackPanel from '../src/components/FeedbackPanel';
import AuditLog from '../src/components/AuditLog';
import CameraView from '../src/components/CameraView';
import App from '../src/App';

const checklist = JSON.parse(readFileSync('../backend/fixtures/checklist.json', 'utf8'));
const id = '08332ca6-c938-47b2-80ef-751badbc3e56';
const snapshot = (): Session => ({ session_id: id, created_at: '2026-10-27T06:00:00Z', mock_mode: true,
  reviewed_at: '2026-10-27T06:01:00Z', checklist: structuredClone(checklist), complete: false, audit_log: [], steps: [
    { step_id: 1, status: 'ACTIVE', passed_via: null, last_verdict: null },
    { step_id: 2, status: 'LOCKED', passed_via: null, last_verdict: null },
  ] });
const checked = (verdict: VerifyResult['verdict'] = 'unsure'): VerifyResult => ({ step_id: 1, verdict,
  confidence: .8, found_counts: { 'yellow plate': 1 }, expected_counts: { 'yellow plate': 1 },
  issues: [], message: 'Please check Step 1.', fix_hint: 'Improve the lighting.', latency_ms: 234,
  next_step_unlocked: verdict === 'pass', masks: [{ label: 'yellow plate', box: [100, 80, 500, 400], status: 'ok', mask_png_base64: '' }] });
const originals = new Map(['fetch', 'document', 'Image', 'window', 'SpeechSynthesisUtterance'].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
function replace(key: string, value: unknown) { Object.defineProperty(globalThis, key, { value, configurable: true, writable: true }); }
afterEach(() => { for (const [key, descriptor] of originals) {
  if (descriptor) Object.defineProperty(globalThis, key, descriptor); else Reflect.deleteProperty(globalThis, key);
} });
function reply(body: unknown, status = 200, headers = {}) {
  replace('fetch', async () => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } }));
}

test('wide and tall sources preserve aspect ratio inside the 640×480 frame', () => {
  assert.deepEqual(containRect(1920, 1080, 640, 480), { x: 0, y: 60, width: 640, height: 360 });
  assert.deepEqual(containRect(480, 640, 640, 480), { x: 140, y: 0, width: 360, height: 480 });
});
test('capture letterboxes without mirroring and sends raw JPEG base64', () => {
  const draws: unknown[][] = [];
  const context = { fillRect: (...args: unknown[]) => draws.push(args), drawImage: (...args: unknown[]) => draws.push(args) };
  const canvas = { width: 0, height: 0, getContext: () => context, toDataURL: (mime: string) => { assert.equal(mime, 'image/jpeg'); return 'data:image/jpeg;base64,FRAME'; } };
  replace('document', { createElement: () => canvas });
  const video = { videoWidth: 1920, videoHeight: 1080, readyState: 2 } as HTMLVideoElement;
  assert.deepEqual(captureFrame(video), { dataUrl: 'data:image/jpeg;base64,FRAME', base64: 'FRAME', width: 640, height: 480 });
  assert.deepEqual(draws, [[0, 0, 640, 480], [video, 0, 60, 640, 360]]);
});
test('capture rejects an unready or zero-sized camera', () => {
  assert.throws(() => captureFrame({ videoWidth: 0, videoHeight: 0, readyState: 0 } as HTMLVideoElement), /Wait for the camera/);
});
test('unsure makes both ok and bad detections amber', () => {
  assert.equal(overlayColor(checked(), 'ok'), colors.unsure);
  assert.equal(overlayColor(checked(), 'bad'), colors.unsure);
  assert.equal(overlayColor(checked('fail'), 'bad'), colors.bad);
  assert.equal(overlayColor(checked('pass'), 'ok'), colors.ok);
});
test('missing part regions need supported location evidence', () => {
  const result = checked('fail');
  result.issues = [{ type: 'missing', part: 'black pin', location_hint: 'assembly area', message: 'One pin missing.' }];
  const step = structuredClone(checklist.steps[1]);
  assert.deepEqual(missingZones(result, step), []);
  result.issues[0].location_hint = 'top-right';
  assert.deepEqual(missingZones(result, step), [{ label: 'Expected black pin', box: [300, 80, 500, 240] }]);
  step.spatial_rules[0].relation = 'bottom_left';
  assert.deepEqual(missingZones(result, step)[0].box, [100, 240, 300, 400]);
  result.verdict = 'unsure';
  assert.deepEqual(missingZones(result, step), []);
  result.verdict = 'fail'; result.masks = [];
  assert.deepEqual(missingZones(result, step), []);
});
test('cancelled overlay work cannot draw onto a newer captured frame', async () => {
  let draws = 0;
  const context = { strokeRect: () => draws++ };
  const canvas = { getContext: () => context } as unknown as HTMLCanvasElement;
  await drawOverlay(canvas, checked(), undefined, { width: 640, height: 480, dataUrl: '', base64: '' }, () => true);
  assert.equal(draws, 0);
});
test('invalid mask images retain detection boxes and report the fallback', async () => {
  replace('Image', class { async decode() { throw new Error('bad image'); } });
  const boxes: unknown[][] = [];
  const context = { setLineDash() {}, strokeRect: (...args: unknown[]) => boxes.push(args), measureText: () => ({ width: 50 }), fillRect() {}, fillText() {} };
  const result = checked(); result.masks[0].mask_png_base64 = 'invalid';
  const failed = await drawOverlay({ getContext: () => context } as unknown as HTMLCanvasElement, result, undefined,
    { width: 640, height: 480, dataUrl: '', base64: '' }, () => false);
  assert.equal(failed, true);
  assert.deepEqual(boxes, [[100, 80, 400, 320]]);
  assert.equal(context.strokeStyle, colors.unsure);
});
test('mask foreground is tinted while background remains transparent', async () => {
  replace('Image', class { width = 2; height = 1; async decode() {} });
  const data = new Uint8ClampedArray([255, 255, 255, 255, 0, 0, 0, 255]);
  let pixels: Uint8ClampedArray | undefined;
  const layer = { getContext: () => ({ drawImage() {}, getImageData: () => ({ data }), putImageData: (image: { data: Uint8ClampedArray }) => { pixels = image.data; } }) };
  replace('document', { createElement: () => layer });
  let layers = 0;
  const context = { drawImage: () => layers++, setLineDash() {}, strokeRect() {}, measureText: () => ({ width: 50 }), fillRect() {}, fillText() {} };
  const result = checked(); result.masks[0].mask_png_base64 = 'test';
  assert.equal(await drawOverlay({ getContext: () => context } as unknown as HTMLCanvasElement, result, undefined,
    { width: 2, height: 1, dataUrl: '', base64: '' }, () => false), false);
  assert.deepEqual([...pixels!], [239, 188, 104, 48, 239, 188, 104, 0]);
  assert.equal(layers, 1);
});
test('speech happens once per result, cancels previous speech, and respects mute', () => {
  const events: string[] = [];
  const speaker = createSpeaker({ cancel: () => events.push('cancel'), speak: message => events.push(message) });
  speaker.speak(1, 'first'); speaker.speak(1, 'duplicate');
  speaker.setMuted(true); speaker.speak(2, 'muted'); speaker.setMuted(false); speaker.speak(3, 'next'); speaker.cancel();
  assert.deepEqual(events, ['cancel', 'first', 'cancel', 'cancel', 'next', 'cancel']);
});
test('missing or failing browser speech leaves the written feedback path usable', () => {
  assert.equal(browserSpeech(), null);
  const missing = createSpeaker(null); assert.equal(missing.supported, false); missing.speak(1, 'text');
  const failing = createSpeaker({ cancel: () => { throw Error(); }, speak: () => { throw Error(); } });
  assert.doesNotThrow(() => { failing.speak(1, 'text'); failing.setMuted(true); });
});
test('compiler accepts the direct checklist and requires a valid session header', async () => {
  const file = new File(['%PDF-1.4'], 'manual.pdf', { type: 'application/pdf' });
  reply(checklist); await assert.rejects(api.compileManual(file), /valid session ID/);
  reply(checklist, 200, { 'X-StepGuard-Session-ID': id }); assert.equal(await api.compileManual(file), id);
});
test('file validation prevents invalid uploads before fetch', async () => {
  replace('fetch', () => assert.fail('invalid files must not be posted'));
  for (const file of [new File([], 'empty.pdf', { type: 'application/pdf' }), new File(['text'], 'image.png', { type: 'image/png' }),
    new File([new Uint8Array(10 * 1024 * 1024 + 1)], 'large.pdf', { type: 'application/pdf' })]) {
    await assert.rejects(api.compileManual(file), api.ApiError);
  }
});
test('PDF without browser MIME metadata is normalized in multipart upload', async () => {
  replace('fetch', async (path: string, init: RequestInit) => {
    assert.equal(path, '/api/compile-manual'); assert.equal(init.cache, 'no-store');
    const file = (init.body as FormData).get('file') as File;
    assert.equal(file.type, 'application/pdf'); assert.equal(file.name, 'manual.PDF');
    return new Response(JSON.stringify(checklist), { headers: { 'X-StepGuard-Session-ID': id } });
  });
  assert.equal(await api.compileManual(new File(['%PDF-1.4'], 'manual.PDF')), id);
});
test('session responses must match the requested identity', async () => {
  reply(snapshot()); assert.equal((await api.getSession(id)).steps[1].status, 'LOCKED');
  reply({ ...snapshot(), session_id: '18332ca6-c938-47b2-80ef-751badbc3e56' });
  await assert.rejects(api.getSession(id), /different session/);
});
test('health and session preserve the selected provider and reject unknown providers', async () => {
  for (const provider of ['meta', 'gemini'] as const) {
    reply({ status: 'ok', mock_mode: false, milestone: 'M6', model_adapters_ready: true, provider });
    assert.equal((await api.getHealth()).provider, provider);
    reply({ ...snapshot(), mock_mode: false, provider });
    assert.equal((await api.getSession(id)).provider, provider);
  }
  reply({ status: 'ok', mock_mode: false, milestone: 'M6', model_adapters_ready: true, provider: 'unknown' });
  await assert.rejects(api.getHealth(), /unexpected response/);
  reply({ ...snapshot(), provider: 'unknown' });
  await assert.rejects(api.getSession(id), /unexpected response/);
});
test('verification posts only the captured image and checks returned step identity', async () => {
  replace('fetch', async (path: string, init: RequestInit) => {
    assert.equal(path, '/api/verify-step'); assert.deepEqual(JSON.parse(init.body as string), { session_id: id, step_id: 1, image_base64: 'FRAME' });
    return new Response(JSON.stringify(checked()));
  });
  assert.equal((await api.verifyStep(id, 1, 'FRAME')).verdict, 'unsure');
  reply({ ...checked(), step_id: 2 }); await assert.rejects(api.verifyStep(id, 1, 'FRAME'), /different step/);
});
test('malformed verdicts, counts, confidence and boxes are rejected', async () => {
  for (const change of [{ verdict: 'maybe' }, { confidence: 2 }, { found_counts: { pin: -1 } }, { masks: [{ label: 'plate', box: [2, 0, 1, 1], status: 'ok', mask_png_base64: '' }] }]) {
    reply({ ...checked(), ...change }); await assert.rejects(api.verifyStep(id, 1, 'FRAME'), /unexpected response/);
  }
});
test('API errors preserve actionable backend messages and hide rejected input', async () => {
  reply({ detail: 'This step is locked.' }, 409); await assert.rejects(api.verifyStep(id, 2, 'PRIVATE_FRAME'), /This step is locked/);
  reply({ detail: [{ input: 'PRIVATE_FRAME' }] }, 422);
  await assert.rejects(api.verifyStep(id, 1, 'PRIVATE_FRAME'), error => error instanceof api.ApiError && !error.message.includes('PRIVATE_FRAME'));
  replace('fetch', async () => { throw Error('network'); }); await assert.rejects(api.getHealth(), error => error.status === 0);
});
test('abort remains an abort and is not relabeled as a backend outage', async () => {
  replace('fetch', async () => { throw new DOMException('Cancelled', 'AbortError'); });
  await assert.rejects(api.getHealth(), error => error.name === 'AbortError');
});
test('override sends the trimmed reason and rejects an automatic-pass response', async () => {
  const response = { session_id: id, step_id: 1, status: 'PASSED', passed_via: 'override', reason: 'Inspected manually', next_step_unlocked: true };
  replace('fetch', async (_path: string, init: RequestInit) => {
    assert.equal(JSON.parse(init.body as string).reason, 'Inspected manually'); return new Response(JSON.stringify(response));
  });
  assert.equal((await api.overrideStep(id, 1, '  Inspected manually  ')).passed_via, 'override');
  reply({ ...response, passed_via: 'automatic' }); await assert.rejects(api.overrideStep(id, 1, 'reason'), /unexpected response/);
});
const feedback = (result: VerifyResult | null, extra = {}) => renderToStaticMarkup(<FeedbackPanel result={result} override={null} muted={false}
  speechSupported canOverride currentStepId={1} busy={false} onMute={() => {}} onOverride={async () => true} {...extra} />);
test('retry feedback appears only after the server reports an actual retry', () => {
  assert.doesNotMatch(feedback(null, { checkingStep: 1, retryCount: 0 }), /Checking again/);
  const html = feedback(null, { checkingStep: 1, retryCount: 1 });
  assert.match(html, /Checking again after a temporary model error/);
  assert.match(html, /next step stays locked/);
});
test('feedback renders distinct fail, unsure, and pass states with hint and latency', () => {
  for (const verdict of ['fail', 'unsure', 'pass'] as const) {
    const html = feedback(checked(verdict));
    assert.match(html, new RegExp(`tone-${verdict}`)); assert.match(html, /Improve the lighting/); assert.match(html, /0.23 s/);
    assert.match(html, verdict === 'pass' ? /Next step unlocked/ : /Next step locked/);
    if (verdict === 'fail') assert.match(html, /Step 1 · Needs correction/);
  }
});
test('manual override is labeled separately and requires a reason', () => {
  const html = feedback(checked(), { override: { session_id: id, step_id: 1, status: 'PASSED', passed_via: 'override', reason: '<manual>', next_step_unlocked: true } });
  assert.match(html, /tone-manual/); assert.match(html, /This is not an automatic pass/); assert.match(html, /&lt;manual&gt;/);
  assert.match(html, /textarea[^>]*required/); assert.match(html, /type="submit" disabled/);
});
test('locked steps are noninteractive and manual progression preserves provenance', () => {
  const session = snapshot();
  let html = renderToStaticMarkup(<Checklist session={session} />);
  assert.match(html, /state-locked/); assert.doesNotMatch(html, /<button/);
  session.steps[0] = { step_id: 1, status: 'PASSED', passed_via: 'override', last_verdict: 'unsure' }; session.steps[1].status = 'ACTIVE';
  html = renderToStaticMarkup(<Checklist session={session} />);
  assert.match(html, /was-overridden/); assert.match(html, /MANUAL OVERRIDE/); assert.match(html, /aria-valuenow="1"/);
});
test('Gemini checklists identify demo evidence while mock mode keeps its development label', () => {
  const session = { ...snapshot(), provider: 'gemini' as const, mock_mode: false };
  assert.match(renderToStaticMarkup(<Checklist session={session} />), /GEMINI DEMO CHECKLIST/);
  session.mock_mode = true;
  const html = renderToStaticMarkup(<Checklist session={session} />);
  assert.match(html, /DEVELOPMENT CHECKLIST/);
  assert.doesNotMatch(html, /GEMINI DEMO CHECKLIST/);
});
test('audit log displays server reasons as escaped text', () => {
  const html = renderToStaticMarkup(<AuditLog entries={[{ timestamp: '2026-10-27T06:00:00Z', event: 'override', step_id: 1, details: { reason: '<script>alert(1)</script>' } }]} />);
  assert.match(html, /Step 1 manually overridden/); assert.match(html, /&lt;script&gt;/); assert.doesNotMatch(html, /<script>/);
});
test('camera is opt-in and completed sessions have a useful final state', () => {
  const props = { frame: null, result: null, checking: false, disabled: false, canCheck: false, onReady() {}, onCheck() {}, onResume() {} };
  const initial = renderToStaticMarkup(<CameraView {...props} complete={false} />);
  assert.match(initial, /Enable camera/); assert.match(initial, /Camera starts only when you enable it/); assert.match(initial, /disabled/);
  assert.match(renderToStaticMarkup(<CameraView {...props} complete />), /ASSEMBLY COMPLETE/);
});
test('initial app renders without starting a camera or assuming a backend mode', () => {
  const html = renderToStaticMarkup(<App />);
  assert.match(html, /MODE UNKNOWN/); assert.match(html, /Choose PDF/); assert.match(html, /Automatic step checking/);
});

test('review endpoint requires a matching session with a saved acknowledgment', async () => {
  replace('fetch', async (path: string, init: RequestInit) => {
    assert.equal(path, `/api/session/${id}/review`); assert.equal(init.method, 'POST');
    return new Response(JSON.stringify(snapshot()));
  });
  assert.ok((await api.reviewSession(id)).reviewed_at);
  reply({ ...snapshot(), reviewed_at: null }); await assert.rejects(api.reviewSession(id), /Review could not be confirmed/);
  reply({ ...snapshot(), session_id: '18332ca6-c938-47b2-80ef-751badbc3e56' });
  await assert.rejects(api.reviewSession(id), /Review could not be confirmed/);
  reply({ ...snapshot(), reviewed_at: true }); await assert.rejects(api.getSession(id), /unexpected response/);
});

test('unestablished counts are distinct from a detected zero', () => {
  const result = { ...checked('unsure'), expected_counts: { 'yellow plate': 1, 'black pin': 4 }, found_counts: { 'yellow plate': 0 } };
  const html = renderToStaticMarkup(<CameraView frame={null} result={result} complete={false} checking={false} disabled canCheck={false} onReady={() => {}} onCheck={() => {}} onResume={() => {}} />);
  assert.match(html, /yellow plate: expected 1, detected 0/);
  assert.match(html, /black pin: expected 4, detected not established/);
  assert.match(html, /Counts are unverified/);
  assert.doesNotMatch(html, /black pin: expected 4, detected 0/);
});

test('external camera action does not create a duplicate check button', () => {
  const html = renderToStaticMarkup(<CameraView showAction={false} frame={null} result={null} complete={false} checking={false} disabled canCheck={false} onReady={() => {}} onCheck={() => {}} onResume={() => {}} />);
  assert.match(html, /Enable camera/);
  assert.doesNotMatch(html, />Check step/);
});

test('the work order distinguishes a held result from the next unlocked step', () => {
  const session = snapshot();
  session.steps[0].status = 'PASSED';
  session.steps[1].status = 'ACTIVE';
  const html = renderToStaticMarkup(<Checklist session={session} presentedStepId={1}/>);
  assert.match(html, /state-passed[^>]*aria-current="step"/);
  assert.match(html, /UNLOCKED/);
  assert.doesNotMatch(html, /CURRENT/);
});
