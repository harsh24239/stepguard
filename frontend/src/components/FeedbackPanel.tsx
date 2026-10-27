import { useEffect, useRef, useState, type FormEvent } from 'react';
import type { OverrideResult, VerifyResult } from '../lib/types';
import Icon from './Icon';

type Props = {
  result: VerifyResult | null;
  override: OverrideResult | null;
  checkingStep?: number;
  retryCount?: number;
  muted: boolean;
  speechSupported: boolean;
  canOverride: boolean;
  currentStepId?: number;
  busy: boolean;
  onMute: () => void;
  onOverride: (reason: string) => Promise<boolean>;
  awaitingContinue?: boolean;
  canContinue?: boolean;
  onContinue?: () => void;
  complete?: boolean;
};

export default function FeedbackPanel(props: Props) {
  const [reason, setReason] = useState('');
  const [overrideOpen, setOverrideOpen] = useState(false);
  const panel = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!props.checkingStep && (props.result || props.override) && window.matchMedia('(max-width: 800px)').matches) {
      panel.current?.scrollIntoView({ block: 'nearest' });
    }
  }, [props.result, props.override, props.checkingStep]);
  const result = props.result;
  const tone = props.checkingStep ? 'checking' : props.override ? 'manual' : result?.verdict ?? 'idle';
  const heading = props.checkingStep ? `Step ${props.checkingStep} · ${props.retryCount ? 'Checking again' : 'Checking'}` : props.override ? `Step ${props.override.step_id} · Manually overridden` :
    result ? `Step ${result.step_id} · ${result.verdict === 'fail' ? 'Needs correction' : result.verdict === 'pass' ? 'Passed' : 'Unable to verify'}` : props.complete ? 'Inspection complete' : 'Ready to check';

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!reason.trim() || !props.canOverride) return;
    if (await props.onOverride(reason)) { setReason(''); setOverrideOpen(false); }
  }

  return <section ref={panel} className={`panel feedback-panel tone-${tone}`} aria-labelledby="feedback-title">
    <div className="panel-heading"><h2 id="feedback-title">Step feedback</h2>
      <button className="icon-button" disabled={!props.speechSupported} onClick={props.onMute} aria-label={props.muted ? 'Unmute spoken feedback' : 'Mute spoken feedback'} aria-pressed={props.muted} title={props.speechSupported ? 'Browser spoken feedback' : 'Speech is unavailable in this browser'}>
        <Icon name={props.muted || !props.speechSupported ? 'mute' : 'speaker'} size={16} />
      </button>
    </div>
    <div className="feedback-body" role="status" aria-live="polite" aria-atomic="true">
      <span className="feedback-heading">{props.checkingStep ? <span className="spinner" /> : <Icon name={result?.verdict === 'pass' && !props.override ? 'check' : tone === 'idle' ? 'shield' : 'alert'} size={16} />}{heading}</span>
      <p className="feedback-message">{props.checkingStep ? props.retryCount ? 'Checking again after a temporary model error. The next step stays locked.' : 'Checking the captured frame. The next step stays locked.' : props.override ? 'Passed by manual override.' : result?.message ?? (props.complete ? 'All steps are complete. Check the history for automatic passes and any manual overrides.' : 'Finish a step, then use Check step to capture your workbench.')}</p>
      {!props.checkingStep && (props.override ? <div className="fix-hint"><span>REASON RECORDED</span><p>{props.override.reason}</p><p className="override-note">{props.override.next_step_unlocked ? 'The next step was unlocked manually.' : 'The session was completed manually.'} This is not an automatic pass.</p></div> : result ? <>
        <div className="fix-hint"><span>{result.verdict === 'pass' ? 'NEXT' : 'WHAT TO DO'}</span><p>{result.fix_hint}</p></div>
        {result.issues.length > 0 && <ul className="issue-list">{result.issues.map((issue, index) => <li key={`${index}-${issue.type}`}>{issue.message}</li>)}</ul>}
        <div className="result-meta"><span>Checked in {(result.latency_ms / 1000).toFixed(result.latency_ms < 1000 ? 2 : 1)} s</span><span>{result.next_step_unlocked ? 'Next step unlocked' : result.verdict === 'pass' ? 'Final step passed' : 'Next step locked'}</span></div>
      </> : !props.complete && <p className="feedback-muted">A pass unlocks the next step. An unsure result keeps it locked.</p>)}
    </div>
    {props.awaitingContinue && <div className="continue-controls"><button className="button primary" disabled={!props.canContinue} onClick={props.onContinue}>{props.complete ? 'Finish inspection' : 'Continue to next step'}<Icon name="arrow" /></button>
      {!props.canContinue && <p>Wait for the current action to finish. If session refresh failed, refresh the session to confirm progression.</p>}
    </div>}
    {!props.speechSupported && <p className="speech-note">Speech is unavailable in this browser. Written feedback is always shown.</p>}
    {props.currentStepId !== undefined && <details className="override-details" open={overrideOpen} onToggle={event => setOverrideOpen(event.currentTarget.open)}>
      <summary>Manual override <span>Reason required</span></summary>
      <form onSubmit={event => void submit(event)}>
        <p>Pass step {props.currentStepId} manually. The reason and time will be recorded. This local prototype does not authenticate a supervisor.</p>
        <label htmlFor="override-reason">Reason for overriding step {props.currentStepId}</label>
        <textarea id="override-reason" value={reason} onChange={event => setReason(event.target.value)} maxLength={1000} required rows={3} disabled={!props.canOverride} placeholder="Explain what you checked manually…" />
        <button className="button secondary small" type="submit" disabled={!props.canOverride || !reason.trim() || props.busy}>Record manual override</button>
      </form>
    </details>}
  </section>;
}
