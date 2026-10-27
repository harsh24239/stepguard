import type { Session } from '../lib/types';
import Icon from './Icon';

export default function Checklist({ session, checkingStep, presentedStepId }: { session: Session | null; checkingStep?: number; presentedStepId?: number }) {
  const passed = session?.steps.filter(step => step.status === 'PASSED').length ?? 0;
  return <section className="panel checklist-panel" aria-labelledby="checklist-title">
    <div className="panel-heading"><h2 id="checklist-title">Assembly checklist</h2><span className="step-count">{session ? `${passed} / ${session.steps.length}` : 'NO MANUAL'}</span></div>
    {!session ? <div className="empty-state"><span className="empty-icon"><Icon name="lock" size={22} /></span><h3>Your instructions, one step at a time.</h3><p>Upload an assembly PDF to create the checklist. Later steps stay locked until the current step passes.</p></div> : <>
      <div className="checklist-product"><span className="eyebrow">{session.mock_mode ? 'DEVELOPMENT CHECKLIST' : session.provider === 'gemini' ? 'GEMINI DEMO CHECKLIST' : 'ASSEMBLY'}</span><h3>{session.checklist.product}</h3>
        <div className="progress-track" role="progressbar" aria-label="Steps passed" aria-valuemin={0} aria-valuemax={session.steps.length} aria-valuenow={passed}><span style={{ width: `${passed / session.steps.length * 100}%` }} /></div>
      </div>
      <div className="step-map" role="list" aria-label="Step progress map">{session.steps.map(step => <span key={step.step_id} role="listitem" className={`step-map-item map-${step.status.toLowerCase()} ${step.passed_via === 'override' ? 'map-override' : ''}`} title={`Step ${step.step_id}: ${step.passed_via === 'override' ? 'manually overridden' : step.status.toLowerCase()}`} aria-label={`Step ${step.step_id}: ${step.passed_via === 'override' ? 'manually overridden' : step.status.toLowerCase()}`}>{step.status === 'PASSED' ? <Icon name="check" size={12}/> : step.step_id}</span>)}</div>
      <details className="step-navigation"><summary>View all {session.steps.length} steps</summary><ol className="checklist">
        {session.checklist.steps.map((step, index) => {
          const state = session.steps[index];
          const status = checkingStep === step.step_id ? 'CHECKING' : state.status;
          return <li key={step.step_id} className={`checklist-step state-${status.toLowerCase()} ${state.passed_via === 'override' ? 'was-overridden' : ''}`} aria-current={(presentedStepId ? presentedStepId === step.step_id : ['ACTIVE', 'FAILED', 'UNSURE', 'CHECKING'].includes(status)) ? 'step' : undefined}>
            <span className="step-number">{status === 'LOCKED' ? <Icon name="lock" size={13} /> : status === 'PASSED' ? <Icon name="check" size={15} /> : status === 'CHECKING' ? <span className="spinner" /> : String(step.step_id).padStart(2, '0')}</span>
            <div className="step-copy"><div className="step-title"><h3>Step {step.step_id}</h3><span className="state-label">{state.passed_via === 'override' ? 'MANUAL OVERRIDE' : status === 'ACTIVE' ? 'CURRENT' : status === 'UNSURE' ? 'UNSURE' : status === 'FAILED' ? 'BLOCKED' : status}</span></div>
              <details className="step-instruction"><summary>View instruction</summary><p>{step.instruction}</p></details>
              {status !== 'LOCKED' && status !== 'PASSED' && <span className="expected-parts">{Object.entries(step.expected_counts).map(([part, count]) => `${count} × ${part}`).join(' · ')}</span>}
            </div>
          </li>;
        })}
      </ol></details>
      {session.complete && <p className="session-complete"><Icon name="check" size={16} />All steps passed{session.steps.some(step => step.passed_via === 'override') ? ' · includes manual overrides' : ''}.</p>}
    </>}
  </section>;
}
