import test from 'node:test';
import assert from 'node:assert/strict';
import { renderToStaticMarkup } from 'react-dom/server';
import { readFileSync } from 'node:fs';
import { inspectionState } from '../src/lib/workflow';
import RequirementsReview from '../src/components/Requirements';
import FeedbackPanel from '../src/components/FeedbackPanel';
import type { Session, VerifyResult, OverrideResult } from '../src/lib/types';

const checklist = JSON.parse(readFileSync('../backend/fixtures/checklist.json', 'utf8'));
const session = (): Session => ({ session_id: '08332ca6-c938-47b2-80ef-751badbc3e56', created_at: '2026-10-27',
  mock_mode: true, reviewed_at: '2026-10-27', checklist: structuredClone(checklist), complete: false, audit_log: [],
  steps: [{ step_id: 1, status: 'ACTIVE', passed_via: null, last_verdict: null }, { step_id: 2, status: 'LOCKED', passed_via: null, last_verdict: null }] });
const result = (): VerifyResult => ({ step_id: 1, verdict: 'pass', confidence: .9, message: 'Test pass', fix_hint: 'Continue',
  found_counts: {}, expected_counts: {}, issues: [], masks: [], latency_ms: 10, next_step_unlocked: true });
const override = (): OverrideResult => ({ session_id: session().session_id, step_id: 1, status: 'PASSED', passed_via: 'override', reason: 'Test only', next_step_unlocked: true });

test('unreviewed, stale, and checking sessions cannot act', () => {
  const s = session(); s.reviewed_at = null;
  assert.equal(inspectionState(s, null, null, true).canAct, false);
  s.reviewed_at = 'reviewed';
  assert.equal(inspectionState(s, null, null, false).canAct, false);
  s.steps[0].status = 'CHECKING';
  assert.equal(inspectionState(s, null, null, true).canAct, false);
});
test('a pass holds the checked instruction and prevents voice, motion, and overrides until Continue', () => {
  const s = session(); s.steps[0].status = 'PASSED'; s.steps[1].status = 'ACTIVE';
  const held = inspectionState(s, result(), null, true);
  assert.equal(held.presented?.step_id, 1); assert.equal(held.active?.step_id, 2);
  assert.equal(held.canAct, false); assert.equal(held.canContinue, true);
  const continued = inspectionState(s, null, null, true);
  assert.equal(continued.presented?.step_id, 2); assert.equal(continued.canAct, true);
  assert.equal(continued.awaitingContinue, false);
});
test('Continue cannot trust a result alone or an unrefreshed session', () => {
  const s = session();
  assert.equal(inspectionState(s, result(), null, true).canContinue, false);
  s.steps[0].status = 'PASSED'; s.steps[1].status = 'ACTIVE';
  assert.equal(inspectionState(s, result(), null, false).canContinue, false);
});
test('manual override uses the same acknowledgment hold and final completion is supported', () => {
  const s = session(); s.steps[0].status = 'PASSED'; s.steps[1].status = 'ACTIVE';
  assert.equal(inspectionState(s, null, override(), true).presented?.step_id, 1);
  assert.equal(inspectionState(s, null, override(), true).canAct, false);
  s.steps[1].status = 'PASSED'; s.complete = true;
  const final = inspectionState(s, { ...result(), step_id: 2, next_step_unlocked: false }, null, true);
  assert.equal(final.canContinue, true);
  assert.equal(inspectionState(s, null, null, true).canAct, false);
});
test('fail and uncertainty cannot reveal the next step or Continue', () => {
  const s = session();
  for (const verdict of ['fail', 'unsure'] as const) {
    const state = inspectionState(s, { ...result(), verdict }, null, true);
    assert.equal(state.awaitingContinue, false); assert.equal(state.canContinue, false);
    assert.equal(state.presented?.step_id, 1);
  }
});
test('old failed evidence is never presented as a result for an externally advanced step', () => {
  const s = session(); s.steps[0].status = 'PASSED'; s.steps[1].status = 'ACTIVE';
  const stale = inspectionState(s, { ...result(), verdict: 'fail' }, null, true);
  assert.equal(stale.presented?.step_id, 1); assert.equal(stale.canAct, false);
  assert.equal(inspectionState(s, null, null, true).presented?.step_id, 2);
});
test('review exposes counts, anchor, placement, and acknowledgment before Start', () => {
  const html = renderToStaticMarkup(<RequirementsReview checklist={checklist} disabled={false} busy={false} onStart={() => {}} />);
  assert.match(html, /Reference anchor/); assert.match(html, /Expected parts/);
  assert.match(html, /inside/); assert.match(html, /I reviewed every step/);
  assert.match(html, /button[^>]*disabled/); assert.doesNotMatch(html, /<textarea/);
});
test('feedback holds pass evidence with disabled Continue until state is confirmed', () => {
  const html = renderToStaticMarkup(<FeedbackPanel result={result()} override={null} muted speechSupported
    canOverride={false} busy={false} awaitingContinue canContinue={false} onContinue={() => {}} onMute={() => {}} onOverride={async () => false} />);
  assert.match(html, /Continue to next step/); assert.match(html, /button[^>]*disabled[^>]*>Continue/);
  assert.doesNotMatch(html, /override-reason/);
});
