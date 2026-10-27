import { useState } from 'react';
import type { Checklist, Step } from '../lib/types';

export function StepRequirements({ step }: { step: Step }) {
  return <div className="requirements">
    <div><span className="field-label">Expected parts</span><ul className="part-chips">{Object.entries(step.expected_counts).map(([part, count]) => <li key={part}><strong>{count} ×</strong> {part}</li>)}</ul></div>
    <div className="requirement-details"><p><strong>Reference anchor:</strong> {step.zone_anchor}</p>
      {step.spatial_rules.length ? <ul>{step.spatial_rules.map((rule, index) => <li key={index}>{rule.part} · {rule.relation.replaceAll('_', ' ')} · {rule.target}</li>)}</ul> : <p>No spatial requirement was extracted for this step.</p>}
    </div>
  </div>;
}

export default function RequirementsReview({ checklist, busy, disabled, onStart }: {
  checklist: Checklist; busy: boolean; disabled: boolean; onStart: () => void;
}) {
  const [acknowledged, setAcknowledged] = useState(false);
  return <section className="panel review-panel" aria-labelledby="review-title">
    <div className="review-intro"><span className="eyebrow">02 / REVIEW REQUIREMENTS</span><h2 id="review-title">Check the checklist against your manual.</h2>
      <p>Confirm the instructions, part counts, reference anchors, and placement requirements. If anything is wrong, correct the manual or compiler and upload again before starting.</p>
      <p className="supporting">Visual checks cannot establish torque, tightness, or other hidden properties. These require human review. Acknowledging this checklist does not prove the model extracted it correctly.</p>
    </div>
    <ol className="review-steps">{checklist.steps.map(step => <li key={step.step_id}>
      <div className="review-step-heading"><span className="step-number">{step.step_id}</span><h3>{step.instruction}</h3></div>
      <StepRequirements step={step} />
    </li>)}</ol>
    <div className="review-start"><label className="checkbox-label"><input type="checkbox" checked={acknowledged} onChange={event => setAcknowledged(event.target.checked)} disabled={busy} />I reviewed every step against the manual.</label>
      <button className="button primary" disabled={!acknowledged || disabled || busy} onClick={onStart}>{busy ? 'Starting…' : 'Start inspection'}</button>
      <p className="supporting">Camera and inspection controls become available after the server saves this acknowledgment.</p>
    </div>
  </section>;
}
