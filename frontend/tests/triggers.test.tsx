import test, { afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { renderToStaticMarkup } from 'react-dom/server';
import { createMotionDetector, frameDifference, startMotionMonitor } from '../src/lib/motion';
import { browserVoiceEnvironment, createVoiceRecorder, matchVoiceCommand, MAX_AUDIO_BYTES } from '../src/lib/voice';
import * as api from '../src/lib/api';
import VoiceControl from '../src/components/VoiceControl';
import CameraView from '../src/components/CameraView';

const originals = new Map(['fetch', 'document', 'navigator', 'MediaRecorder', 'performance', 'setTimeout', 'clearTimeout'].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
function replace(key: string, value: unknown) { Object.defineProperty(globalThis, key, { value, configurable: true, writable: true }); }
afterEach(() => { for (const [key, descriptor] of originals) {
  if (descriptor) Object.defineProperty(globalThis, key, descriptor); else Reflect.deleteProperty(globalThis, key);
} });
const pixels = (value: number) => new Uint8ClampedArray([value, value, value, 255]);
function moving(detector: ReturnType<typeof createMotionDetector>, start = 0) {
  detector.sample(pixels(0), start); detector.sample(pixels(80), start + 100); detector.sample(pixels(0), start + 200);
}
function still(detector: ReturnType<typeof createMotionDetector>, start: number, end: number) {
  const events: number[] = [];
  for (let time = start; time <= end; time += 100) if (detector.sample(pixels(0), time)) events.push(time);
  return events;
}
test('motion score uses average pixel luminance change and ignores alpha', () => {
  assert.ok(Math.abs(frameDifference(pixels(255), pixels(0)) - 255) < .001);
  assert.equal(frameDifference(new Uint8ClampedArray([0, 0, 0, 0]), pixels(0)), 0);
  assert.throws(() => frameDifference(pixels(0), new Uint8ClampedArray()), /Invalid/);
});
test('stationary frames and a single abrupt change never arm a check', () => {
  const detector = createMotionDetector();
  assert.deepEqual(still(detector, 0, 3000), []);
  detector.sample(pixels(100), 3100);
  for (let time = 3200; time < 5000; time += 100) assert.equal(detector.sample(pixels(100), time), false);
});
test('two motion samples followed by 700ms of stillness trigger exactly once', () => {
  const detector = createMotionDetector(); moving(detector);
  assert.deepEqual(still(detector, 300, 3000), [1000]);
});
test('moderate movement interrupts the stillness timer', () => {
  const detector = createMotionDetector(); moving(detector); still(detector, 300, 700);
  assert.equal(detector.sample(pixels(8), 800), false);
  assert.equal(detector.sample(pixels(0), 900), false);
  assert.deepEqual(still(detector, 1000, 1700), [1700]);
});
test('cooldown and a new movement cycle are required before the next trigger', () => {
  const detector = createMotionDetector(); moving(detector); assert.deepEqual(still(detector, 300, 1000), [1000]);
  moving(detector, 1100); assert.deepEqual(still(detector, 1400, 3000), []);
  moving(detector, 3100); assert.deepEqual(still(detector, 3400, 4100), [4100]);
});
test('a persisted cooldown also applies when monitoring is rearmed', () => {
  const detector = createMotionDetector(2000); moving(detector);
  assert.deepEqual(still(detector, 300, 2500), []);
  moving(detector, 2600); assert.deepEqual(still(detector, 2900, 3600), [3600]);
});
test('reset, suspended sampling, or a new frame size discard old motion', () => {
  for (const action of ['reset', 'gap', 'resize']) {
    const detector = createMotionDetector(); moving(detector);
    if (action === 'reset') detector.reset();
    if (action === 'resize') detector.sample(new Uint8ClampedArray(8), 300);
    assert.deepEqual(still(detector, action === 'gap' ? 2000 : 400, 3000), []);
  }
});
test('motion baseline owns a copy when the browser reuses pixel buffers', () => {
  const detector = createMotionDetector(); const buffer = pixels(0);
  detector.sample(buffer, 0); buffer.fill(80); detector.sample(buffer, 100); buffer.fill(0); detector.sample(buffer, 200);
  assert.deepEqual(still(detector, 300, 1000), [1000]);
});

function monitorHarness() {
  let time = 0, value = 0, nextId = 0, fail = false;
  const timers = new Map<number, () => void>();
  const listeners = new Map<string, () => void>();
  const document = { hidden: false, createElement: () => ({ getContext: () => ({ drawImage() {}, getImageData() { if (fail) throw Error(); return { data: pixels(value) }; } }) }),
    addEventListener: (name: string, callback: () => void) => listeners.set(name, callback), removeEventListener: (name: string) => listeners.delete(name) };
  replace('document', document); replace('performance', { now: () => time });
  replace('setTimeout', (callback: () => void) => { const id = ++nextId; timers.set(id, callback); return id; });
  replace('clearTimeout', (id: number) => timers.delete(id));
  return { document, timers, listeners, video: { readyState: 2, videoWidth: 640, videoHeight: 480 } as HTMLVideoElement,
    fail() { fail = true; }, tick(at: number, brightness: number) {
      time = at; value = brightness; const entry = timers.entries().next().value;
      assert.ok(entry, 'a sample should be scheduled'); timers.delete(entry[0]); entry[1]();
    } };
}
test('motion monitor fires one event, removes its listener, and stops sampling', () => {
  const h = monitorHarness(); let calls = 0;
  startMotionMonitor(h.video, () => calls++, () => assert.fail());
  h.tick(0, 0); h.tick(100, 80); h.tick(200, 0);
  for (let at = 300; at <= 1000; at += 100) h.tick(at, 0);
  assert.equal(calls, 1); assert.equal(h.timers.size, 0); assert.equal(h.listeners.size, 0);
});
test('hidden-tab transitions discard motion before returning to the camera', () => {
  const h = monitorHarness(); let calls = 0;
  const stop = startMotionMonitor(h.video, () => calls++, () => assert.fail());
  h.tick(0, 0); h.tick(100, 80); h.tick(200, 0);
  h.document.hidden = true; h.listeners.get('visibilitychange')!(); h.tick(300, 0);
  h.document.hidden = false; h.listeners.get('visibilitychange')!();
  for (let at = 400; at <= 1400; at += 100) h.tick(at, 0);
  assert.equal(calls, 0); stop(); assert.equal(h.timers.size, 0);
});
test('monitor cleanup and canvas errors stop all sampling', () => {
  const h = monitorHarness(); let errors = 0;
  const stop = startMotionMonitor(h.video, () => assert.fail(), () => errors++);
  stop(); assert.equal(h.timers.size, 0); assert.equal(h.listeners.size, 0);
  startMotionMonitor(h.video, () => assert.fail(), () => errors++); h.fail(); h.tick(100, 0);
  assert.equal(errors, 1); assert.equal(h.timers.size, 0); assert.equal(h.listeners.size, 0);
});
test('voice commands match complete phrases and reject negations and unrelated text', () => {
  for (const text of ['step done', 'Check STEP.', '  NEXT   step! ', 'step\ndone?']) assert.equal(matchVoiceCommand(text), true);
  for (const text of ['', 'do not check step', 'please check step', 'next step then override', 'step 2 done', 'unchecked step']) assert.equal(matchVoiceCommand(text), false);
});

function voiceHarness(options: { pending?: boolean; denied?: boolean; empty?: boolean; broken?: boolean } = {}) {
  let now = 0, acquired = 0, created = 0, stopped = 0, cancelled = 0;
  let grant: (stream: unknown) => void = () => {};
  const grants: (() => void)[] = [];
  const statuses: string[] = [], errors: string[] = [], audio: Blob[] = [];
  const timers = new Map<number, () => void>();
  const track = { onended: null as (() => void) | null, stop() { stopped++; } };
  const stream = { getTracks: () => [track] };
  let recording: FakeRecorder;
  class FakeRecorder {
    state = 'inactive'; mimeType = 'audio/webm;codecs=opus';
    ondataavailable: ((event: { data: Blob }) => void) | null = null;
    onstop: (() => void) | null = null; onerror: (() => void) | null = null;
    start() { if (options.broken) throw Error(); this.state = 'recording'; }
    stop() { this.state = 'inactive'; queueMicrotask(() => {
      this.ondataavailable?.({ data: new Blob(options.empty ? [] : ['AUDIO']) }); this.onstop?.();
    }); }
  }
  const recorder = createVoiceRecorder({ mime: 'audio/webm;codecs=opus',
    async acquire() { acquired++; if (options.denied) throw new DOMException('denied', 'NotAllowedError');
      return options.pending ? await new Promise(resolve => { grant = resolve; grants.push(() => resolve(stream)); }) : stream; },
    recorder() { created++; return recording = new FakeRecorder(); }, now: () => now,
    after(callback, milliseconds) { assert.equal(milliseconds, 5000); timers.set(1, callback); return 1; }, clear: id => timers.delete(id),
  }, { onStatus: status => statuses.push(status), onError: message => errors.push(message), onCancel: () => cancelled++, onAudio: blob => audio.push(blob) });
  return { recorder, statuses, errors, audio, timers, track, stream, grant: () => grant(stream), grantAt: (index: number) => grants[index](),
    at(value: number) { now = value; }, recording: () => recording, counts: () => ({ acquired, created, stopped, cancelled }) };
}
const flush = () => new Promise<void>(resolve => queueMicrotask(resolve));
test('hold and release emit one audio clip and stop the microphone before upload', async () => {
  const h = voiceHarness(); await h.recorder.start(); h.at(800); h.recorder.release(); h.recorder.release();
  assert.equal(h.counts().stopped, 1); assert.equal(h.audio.length, 0);
  await flush(); assert.equal(h.audio.length, 1); assert.equal(h.audio[0].type, 'audio/webm;codecs=opus');
  assert.deepEqual(h.statuses, ['requesting', 'recording', 'stopping', 'idle']); assert.equal(h.timers.size, 0);
});
test('releasing during permission prevents a late grant from recording', async () => {
  const h = voiceHarness({ pending: true }); const pending = h.recorder.start();
  h.recorder.release(); h.grant(); await pending;
  assert.deepEqual(h.counts(), { acquired: 1, created: 0, stopped: 1, cancelled: 1 }); assert.equal(h.audio.length, 0);
});
test('duplicate presses do not request two microphones', async () => {
  const h = voiceHarness(); await Promise.all([h.recorder.start(), h.recorder.start()]);
  assert.equal(h.counts().acquired, 1); assert.equal(h.counts().created, 1); h.recorder.cancel();
});
test('recordings stop automatically at five seconds', async () => {
  const h = voiceHarness(); await h.recorder.start(); h.at(5000); h.timers.get(1)!(); await flush();
  assert.equal(h.audio.length, 1); assert.equal(h.counts().stopped, 1); assert.equal(h.timers.size, 0);
});
test('cancel and dispose discard recordings, handlers, and timers', async () => {
  for (const method of ['cancel', 'dispose'] as const) {
    const h = voiceHarness(); await h.recorder.start(); h.at(900); h.recorder[method](); await flush();
    assert.equal(h.audio.length, 0); assert.equal(h.counts().stopped, 1); assert.equal(h.counts().cancelled, 1);
    assert.equal(h.timers.size, 0); assert.equal(h.track.onended, null);
  }
});
test('too-short and empty recordings cannot become commands', async () => {
  const short = voiceHarness(); await short.recorder.start(); short.at(100); short.recorder.release(); await flush();
  assert.equal(short.audio.length, 0); assert.match(short.errors[0], /longer/);
  const empty = voiceHarness({ empty: true }); await empty.recorder.start(); empty.at(500); empty.recorder.release(); await flush();
  assert.equal(empty.audio.length, 0); assert.match(empty.errors[0], /No audio/); assert.equal(empty.counts().cancelled, 1);
});
test('permission denial and recorder initialization failure free the action', async () => {
  const denied = voiceHarness({ denied: true }); await denied.recorder.start();
  assert.match(denied.errors[0], /denied/); assert.equal(denied.counts().cancelled, 1);
  const broken = voiceHarness({ broken: true }); await broken.recorder.start();
  assert.equal(broken.counts().stopped, 1); assert.equal(broken.counts().cancelled, 1); assert.equal(broken.audio.length, 0);
});
test('microphone disconnect and recording errors cancel without sending audio', async () => {
  for (const source of ['track', 'recorder']) {
    const h = voiceHarness(); await h.recorder.start();
    if (source === 'track') h.track.onended!(); else h.recording().onerror!();
    await flush(); assert.equal(h.audio.length, 0); assert.equal(h.errors.length, 1); assert.equal(h.counts().stopped, 1);
  }
});
test('oversized audio stops immediately and is discarded', async () => {
  const h = voiceHarness(); await h.recorder.start();
  h.recording().ondataavailable!({ data: new Blob([new Uint8Array(MAX_AUDIO_BYTES + 1)]) }); await flush();
  assert.equal(h.audio.length, 0); assert.match(h.errors[0], /too large/); assert.equal(h.counts().stopped, 1);
});
test('unexpected recorder stop does not submit a voice command', async () => {
  const h = voiceHarness(); await h.recorder.start(); h.recording().stop(); await flush();
  assert.equal(h.audio.length, 0); assert.match(h.errors[0], /unexpectedly/);
});
test('a cancelled permission request cannot disturb a later recording', async () => {
  const h = voiceHarness({ pending: true }); const first = h.recorder.start();
  h.recorder.cancel(); const second = h.recorder.start();
  h.grantAt(0); await first;
  assert.equal(h.statuses.at(-1), 'requesting'); assert.equal(h.counts().created, 0);
  h.grantAt(1); await second; h.at(600); h.recorder.release(); await flush();
  assert.equal(h.audio.length, 1); assert.equal(h.counts().created, 1);
});
test('unsupported MediaRecorder implementations fall back to the button', () => {
  replace('navigator', { mediaDevices: { getUserMedia() {} } }); replace('MediaRecorder', undefined);
  assert.equal(browserVoiceEnvironment(), null);
  replace('MediaRecorder', { isTypeSupported: () => false }); assert.equal(browserVoiceEnvironment(), null);
  replace('MediaRecorder', { isTypeSupported: () => { throw Error(); } }); assert.equal(browserVoiceEnvironment(), null);
});
test('audio API sends multipart bytes and validates the explicit mock flag', async () => {
  const audio = new Blob(['\x1a\x45\xdf\xa3'], { type: 'audio/webm;codecs=opus' });
  replace('fetch', async (path: string, init: RequestInit) => {
    assert.equal(path, '/api/transcribe'); assert.equal(init.method, 'POST'); assert.equal(init.cache, 'no-store');
    const file = (init.body as FormData).get('file') as File; assert.equal(file.name, 'command.webm'); assert.equal(file.size, audio.size);
    assert.equal(file.type, 'audio/webm;codecs=opus'); return new Response(JSON.stringify({ text: 'step done', mock_mode: true }));
  });
  assert.deepEqual(await api.transcribe(audio), { text: 'step done', mock_mode: true });
  replace('fetch', async () => new Response(JSON.stringify({ text: 'step done' })));
  await assert.rejects(api.transcribe(audio), /unexpected response/);
});
test('invalid audio is rejected locally without a network request', async () => {
  replace('fetch', () => assert.fail('invalid audio must not be posted'));
  for (const audio of [new Blob([], { type: 'audio/webm' }), new Blob(['text'], { type: 'text/plain' }), new Blob([new Uint8Array(MAX_AUDIO_BYTES + 1)], { type: 'audio/webm' })]) {
    await assert.rejects(api.transcribe(audio), api.ApiError);
  }
});
test('voice UI explains hold behavior, mock recognition, and the button fallback', () => {
  const html = renderToStaticMarkup(<VoiceControl disabled available={false} mockMode message="" onStart={() => false} onAudio={async () => {}} onCancel={() => {}} />);
  assert.match(html, /Hold to record a step command/); assert.match(html, /disabled/); assert.match(html, /Use Check step/);
  assert.match(html, /MOCK transcription always returns/);
});
test('automatic monitoring is opt-in and pauses on a captured frame', () => {
  const props = { result: null, checking: false, disabled: false, canCheck: true, complete: false, onReady() {}, onCheck() {}, onResume() {} };
  let html = renderToStaticMarkup(<CameraView {...props} frame={null} />);
  assert.match(html, /Check when motion stops/); assert.doesNotMatch(html, /checked=""/);
  html = renderToStaticMarkup(<CameraView {...props} autoEnabled onAutoToggle={() => {}} frame={{ dataUrl: 'data:image/jpeg;base64,x', base64: 'x', width: 640, height: 480 }} />);
  assert.match(html, /Resume live view to rearm/);
});
