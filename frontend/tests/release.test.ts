import test, { afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { encodePcmWav, toVoiceWav } from '../src/lib/audio';
import { downloadReport } from '../src/lib/download';
import * as api from '../src/lib/api';
import type { InspectionReport, Session } from '../src/lib/types';

const id = '08332ca6-c938-47b2-80ef-751badbc3e56';
const snapshot = (): Session => ({ session_id: id, created_at: '2026-10-27', mock_mode: true, provider: 'meta', reviewed_at: null,
  checklist: JSON.parse(readFileSync('../backend/fixtures/checklist.json', 'utf8')), complete: false, audit_log: [],
  steps: [{ step_id: 1, status: 'ACTIVE', passed_via: null, last_verdict: null }, { step_id: 2, status: 'LOCKED', passed_via: null, last_verdict: null }] });
const report = (): InspectionReport => ({ format_version: 1, exported_at: '2026-10-27', evidence_label: 'development fixtures', limitations: ['Synthetic test'],
  summary: { total_steps: 2, automatic_passes: 0, manual_overrides: 0, completed_checks: 0, check_errors: 0, complete: false }, session: snapshot() });
const originals = new Map(['fetch', 'document', 'window'].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
const originalCreate = URL.createObjectURL, originalRevoke = URL.revokeObjectURL;
function replace(key: string, value: unknown) { Object.defineProperty(globalThis, key, { value, configurable: true }); }
afterEach(() => { for (const [key, descriptor] of originals) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else Reflect.deleteProperty(globalThis, key); } URL.createObjectURL = originalCreate; URL.revokeObjectURL = originalRevoke; });
function reply(value: unknown) { replace('fetch', async () => new Response(JSON.stringify(value))); }

test('sample onboarding rejects live, already reviewed, and progressed responses', async () => {
  reply(snapshot()); assert.equal((await api.createSampleSession()).reviewed_at, null);
  for (const s of [{ ...snapshot(), mock_mode: false }, { ...snapshot(), reviewed_at: 'reviewed' }, { ...snapshot(), complete: true }]) {
    reply(s); await assert.rejects(api.createSampleSession(), /fresh development checklist/);
  }
  const progressed = snapshot(); progressed.steps[1].status = 'ACTIVE';
  reply(progressed); await assert.rejects(api.createSampleSession(), /fresh development checklist/);
});
test('report validation prevents identity and fixture provenance mixups', async () => {
  reply(report()); assert.equal((await api.getInspectionReport(id)).summary.automatic_passes, 0);
  for (const changed of [{ ...report(), evidence_label: 'recorded provider outcomes' }, { ...report(), session: { ...snapshot(), session_id: '18332ca6-c938-47b2-80ef-751badbc3e56' } }, { ...report(), summary: { ...report().summary, manual_overrides: -1 } }]) {
    reply(changed); await assert.rejects(api.getInspectionReport(id), /unexpected response/);
  }
});
test('WAV encoding produces mono signed 16-bit PCM with correct little-endian headers and clipping', async () => {
  const blob = encodePcmWav(new Float32Array([-2, -1, -.5, 0, .5, 1, 2]));
  const bytes = await blob.arrayBuffer(), view = new DataView(bytes);
  assert.equal(blob.type, 'audio/wav'); assert.equal(blob.size, 58);
  assert.equal(new TextDecoder().decode(bytes.slice(0, 4)), 'RIFF'); assert.equal(new TextDecoder().decode(bytes.slice(8, 12)), 'WAVE');
  assert.equal(view.getUint16(20, true), 1); assert.equal(view.getUint16(22, true), 1);
  assert.equal(view.getUint32(24, true), 16000); assert.equal(view.getUint32(28, true), 32000);
  assert.equal(view.getUint16(34, true), 16); assert.equal(view.getUint32(40, true), 14);
  assert.deepEqual(Array.from({ length: 7 }, (_, i) => view.getInt16(44 + i * 2, true)), [-32768, -32768, -16384, 0, 16384, 32767, 32767]);
});
test('invalid or oversized decoded audio cannot be uploaded as a voice command', () => {
  for (const samples of [new Float32Array(), new Float32Array([NaN]), new Float32Array([Infinity]), new Float32Array(96001)]) assert.throws(() => encodePcmWav(samples), /converted to PCM WAV/);
});
test('recording conversion uses decoded samples and sanitizes decoder failures', async () => {
  const input = new Blob(['COMPRESSED_CONTAINER'], { type: 'audio/webm' });
  const output = await toVoiceWav(input, async bytes => { assert.equal(new TextDecoder().decode(bytes), 'COMPRESSED_CONTAINER'); return new Float32Array([.25, -.25]); });
  assert.equal(output.type, 'audio/wav'); assert.equal(output.size, 48);
  await assert.rejects(toVoiceWav(input, async () => { throw new Error('PRIVATE_DECODER_DETAILS'); }), error => error instanceof Error && !error.message.includes('PRIVATE_DECODER_DETAILS'));
});
test('empty and oversized recording containers are rejected before decoding', async () => {
  const decode = async () => { assert.fail('Must not decode invalid containers'); return new Float32Array(); };
  await assert.rejects(toVoiceWav(new Blob(), decode));
  await assert.rejects(toVoiceWav(new Blob([new Uint8Array(5 * 1024 * 1024 + 1)]), decode));
});
test('report download uses only validated local JSON and cleans up temporary browser resources', async () => {
  const events: string[] = []; let saved: Blob | undefined;
  const link = { href: '', download: '', click() { events.push('click'); }, remove() { events.push('remove'); } };
  replace('document', { createElement: () => link, body: { append: () => events.push('append') } });
  replace('window', { setTimeout(callback: () => void) { callback(); } });
  URL.createObjectURL = blob => { saved = blob as Blob; return 'blob:local-report'; };
  URL.revokeObjectURL = url => { assert.equal(url, 'blob:local-report'); events.push('revoke'); };
  downloadReport(report());
  assert.equal(link.download, `stepguard-${id}.json`); assert.deepEqual(events, ['append', 'click', 'remove', 'revoke']);
  assert.deepEqual(JSON.parse(await saved!.text()), report());
});
