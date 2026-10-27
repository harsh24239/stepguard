// Development-only visual fixture. Vite's production entry never imports this file.
import { useState } from 'react';
import { encodePcmWav, toVoiceWav } from '../src/lib/audio';
import { createRoot } from 'react-dom/client';
import '../src/styles.css';
import CameraView from '../src/components/CameraView';
import Checklist from '../src/components/Checklist';
import FeedbackPanel from '../src/components/FeedbackPanel';
import RequirementsReview, { StepRequirements } from '../src/components/Requirements';
import type { Session, VerifyResult } from '../src/lib/types';

const first = { step_id: 1, instruction: 'Place four black pins inside the yellow plate.', sam_prompts: ['yellow plate', 'black pin'], expected_counts: { 'yellow plate': 1, 'black pin': 4 }, zone_anchor: 'yellow plate', spatial_rules: [{ part: 'black pin', relation: 'inside', target: 'yellow plate' }], fix_hint_template: 'Place four pins inside the plate.' };
const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480"><rect width="640" height="480" fill="#17231f"/><rect x="110" y="90" width="420" height="300" rx="12" fill="#d5b74b"/><g fill="#202621"><circle cx="150" cy="130" r="16"/><circle cx="490" cy="130" r="16"/><circle cx="150" cy="350" r="16"/><circle cx="490" cy="350" r="16"/></g><text x="320" y="246" text-anchor="middle" font-family="sans-serif" font-size="18" fill="#17231f">SYNTHETIC TEST IMAGE</text></svg>';
function Preview() {
  const [state, setState] = useState('pass');
  const [long, setLong] = useState(false);
  const [muted, setMuted] = useState(true);
  const [audioCheck, setAudioCheck] = useState('');
  async function testAudio() {
    try {
      const input = encodePcmWav(Float32Array.from({ length: 2400 }, (_, i) => Math.sin(i / 10) * .25), 24000);
      const output = await toVoiceWav(input);
      const view = new DataView(await output.arrayBuffer());
      if (view.getUint32(24, true) !== 16000 || view.getUint16(22, true) !== 1 || view.getUint16(34, true) !== 16) throw Error();
      setAudioCheck(`Synthetic audio conversion verified: mono, 16-bit PCM, 16000 Hz, ${output.size} bytes. No microphone or model used.`);
    } catch { setAudioCheck('Synthetic audio conversion could not be verified in this browser.'); }
  }
  const steps = Array.from({ length: long ? 50 : 3 }, (_, index) => ({ ...first, step_id: index + 1, instruction: long ? `${first.instruction} Keep all four corners visible, check the reference anchor, and inspect each part carefully before continuing to the next assembly task.` : first.instruction }));
  const session: Session = { session_id: '08332ca6-c938-47b2-80ef-751badbc3e56', created_at: '2026-10-27', reviewed_at: '2026-10-27', mock_mode: true, provider: 'meta', checklist: { product: 'Synthetic assembly fixture', steps }, complete: state === 'complete', audit_log: [], steps: steps.map(step => ({ step_id: step.step_id, status: state === 'complete' ? 'PASSED' : step.step_id === 1 ? state === 'pass' || state === 'override' ? 'PASSED' : 'ACTIVE' : step.step_id === 2 && (state === 'pass' || state === 'override') ? 'ACTIVE' : 'LOCKED', passed_via: null, last_verdict: null })) };
  const verdict = state === 'fail' ? 'fail' : state === 'unsure' ? 'unsure' : 'pass';
  const result: VerifyResult | null = ['pass', 'fail', 'unsure'].includes(state) ? { step_id: 1, verdict, confidence: .8, expected_counts: first.expected_counts, found_counts: { 'yellow plate': 1, 'black pin': state === 'fail' ? 3 : 4 }, issues: state === 'fail' ? [{ type: 'missing', part: 'black pin', location_hint: 'assembly area', message: 'One black pin is missing.' }] : [], message: state === 'fail' ? 'One black pin is missing. The next step stays locked.' : state === 'unsure' ? 'The image does not establish a reliable match. The next step stays locked.' : 'The visible parts match this step.', fix_hint: state === 'pass' ? 'Review the captured evidence, then continue.' : 'Return to live view, make the parts clearly visible, then check again.', masks: [], latency_ms: 1240, next_step_unlocked: state === 'pass' } : null;
  const held = state === 'pass' || state === 'override';
  return <div className="app-body"><main>
    <div className="notice"><p>Synthetic UI fixtures — no provider calls, physical measurements, or automatic passes are demonstrated here.</p></div>
    <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 16, marginBottom: 20 }}><label>UI state <select aria-label="UI state" value={state} onChange={event => setState(event.target.value)}>{['review', 'camera-off', 'checking', 'retrying', 'fail', 'unsure', 'pass', 'override', 'complete'].map(value => <option key={value}>{value}</option>)}</select></label>
      <label className="checkbox-label"><input type="checkbox" checked={long} onChange={event => setLong(event.target.checked)} />Long instructions and 50 steps</label></div>
<div style={{ marginBottom: 20 }}><button className="button secondary" onClick={() => void testAudio()}>Test synthetic WAV conversion</button><p role="status">{audioCheck}</p></div>
    {state === 'review' ? <RequirementsReview checklist={session.checklist} disabled={false} busy={false} onStart={() => setState('camera-off')} /> : <>
      <section className="current-task panel"><span className="eyebrow">{held ? 'CHECKED STEP 1' : 'CURRENT STEP 1'}</span><h2>{steps[0].instruction}</h2><StepRequirements step={steps[0]} /></section>
      <div className="inspection-grid"><CameraView frame={['camera-off', 'complete'].includes(state) ? null : { dataUrl: `data:image/svg+xml,${encodeURIComponent(svg)}`, base64: '', width: 640, height: 480 }} result={result} checkedStep={steps[0]} activeStepId={1} capturedStepId={1} attemptNumber={2} awaitingContinue={held} complete={state === 'complete'} checking={['checking', 'retrying'].includes(state)} disabled={['checking', 'retrying'].includes(state)} canCheck={false} onReady={() => {}} onCheck={() => {}} onResume={() => setState('camera-off')} />
        <div className="result-column"><FeedbackPanel result={result} override={state === 'override' ? { session_id: session.session_id, step_id: 1, status: 'PASSED', passed_via: 'override', reason: 'Synthetic manual override to test presentation.', next_step_unlocked: true } : null} checkingStep={['checking', 'retrying'].includes(state) ? 1 : undefined} retryCount={state === 'retrying' ? 1 : 0} muted={muted} speechSupported onMute={() => setMuted(!muted)} canOverride={!held} currentStepId={held || state === 'complete' ? undefined : 1} busy={false} onOverride={async () => { setState('override'); return true; }} awaitingContinue={held} canContinue onContinue={() => setState('camera-off')} complete={state === 'complete'} /><Checklist session={session} presentedStepId={1} /></div>
      </div></>}
  </main></div>;
}
createRoot(document.getElementById('root')!).render(<Preview />);
