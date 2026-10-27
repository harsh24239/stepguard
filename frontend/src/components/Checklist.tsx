import type { Session } from '../lib/types';
import Icon from './Icon';

export default function Checklist({ session, checkingStep, presentedStepId }: { session: Session | null; checkingStep?: number; presentedStepId?: number }) {
  const passed = session?.steps.filter(step => step.status === 'PASSED').length ?? 0;
  const currentId = presentedStepId ?? session?.steps.find(step => ['ACTIVE', 'FAILED', 'UNSURE', 'CHECKING'].includes(step.status))?.step_id;
  const currentIndex = Math.max(0, session?.checklist.steps.findIndex(step => step.step_id === currentId) ?? 0);
  const nearbyStart = Math.min(Math.max(0, currentIndex - 1), Math.max(0, (session?.steps.length ?? 0) - 3));

  function renderSteps(start: number, end: number) {
    return <ol className="checklist" start={start + 1}>{session?.checklist.steps.slice(start, end).map((step, offset) => {
      const state = session.steps[start + offset];
      const status = checkingStep === step.step_id ? 'CHECKING' : state.status;
      const current = currentId === step.step_id;
      return <li key={step.step_id} className={`checklist-step state-${status.toLowerCase()} ${state.passed_via === 'override' ? 'was-overridden' : ''}`} aria-current={current ? 'step' : undefined}>
        <span className="step-number">{status === 'LOCKED' ? <Icon name="lock" size={13}/> : status === 'PASSED' ? <Icon name="check" size={15}/> : status === 'CHECKING' ? <span className="spinner"/> : String(step.step_id).padStart(2, '0')}</span>
        <div className="step-copy"><div className="step-title"><h3>Step {String(step.step_id).padStart(2, '0')}</h3><span className="state-label">{state.passed_via === 'override' ? 'MANUAL OVERRIDE' : status === 'ACTIVE' ? current ? 'CURRENT' : 'UNLOCKED' : status === 'FAILED' ? 'BLOCKED' : status}</span></div>
          <details className="step-instruction"><summary>View instruction</summary><p>{step.instruction}</p></details>
        </div>
      </li>;
    })}</ol>;
  }

  return <section className="checklist-panel" aria-labelledby="checklist-title">
    <div className="work-order-heading"><h2 id="checklist-title">Work order</h2><span className="step-count">{session ? `${passed} / ${session.steps.length} passed` : 'NO MANUAL'}</span></div>
    {!session ? <div className="empty-state"><h3>No procedure loaded.</h3><p>Upload an assembly PDF to create the checklist.</p></div> : <>
      <div className="checklist-product"><span className="eyebrow">{session.mock_mode ? 'DEVELOPMENT CHECKLIST' : session.provider === 'gemini' ? 'GEMINI DEMO CHECKLIST' : 'ASSEMBLY CHECKLIST'}</span><h3>{session.checklist.product}</h3>
        <div className="progress-track" role="progressbar" aria-label="Steps passed" aria-valuemin={0} aria-valuemax={session.steps.length} aria-valuenow={passed}><span style={{ width: `${passed / session.steps.length * 100}%` }}/></div>
      </div>
      {renderSteps(nearbyStart, nearbyStart + 3)}
      <details className={`step-navigation ${session.steps.length <= 3 ? 'small-procedure' : ''}`}><summary>View all {session.steps.length} steps</summary>{renderSteps(0, session.steps.length)}</details>
      {session.complete && <p className="session-complete"><Icon name="check" size={16}/>All steps passed{session.steps.some(step => step.passed_via === 'override') ? ' · includes manual overrides' : ''}.</p>}
    </>}
  </section>;
}
