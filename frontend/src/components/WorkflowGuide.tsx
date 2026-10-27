import { forwardRef } from 'react';
import Icon from './Icon';

const WorkflowGuide = forwardRef<HTMLDialogElement, { mockMode: boolean }>(function WorkflowGuide({ mockMode }, ref) {
  return <dialog ref={ref} className="workflow-dialog" aria-labelledby="guide-title" onClick={event => { if (event.target === event.currentTarget) event.currentTarget.close(); }}>
    <div className="guide-heading"><span className="eyebrow">A QUICK WALKTHROUGH</span><form method="dialog"><button className="icon-button" aria-label="Close workflow guide"><Icon name="close"/></button></form></div>
    <h2 id="guide-title">From manual to checked assembly.</h2><p className="guide-description">One procedure, one workbench, one step at a time.</p>
    <ol className="guide-steps">
      <li><span className="guide-number">01</span><div><h3>Bring your procedure</h3><p>Upload a PDF, then compare the extracted instructions, counts, reference anchors, and placement rules with the manual.</p></div></li>
      <li><span className="guide-number">02</span><div><h3>Frame your workbench</h3><p>Enable the camera when you are ready. Keep the assembly visible from above with even lighting. Finish the current step, then select Check step.</p></div></li>
      <li><span className="guide-number">03</span><div><h3>Review the evidence</h3><p>A pass unlocks the following step; Continue presents it. A correction or uncertain result keeps it locked. Manual overrides require a reason and stay visibly identified.</p></div></li>
    </ol>
    <div className="guide-limit"><Icon name="alert"/><p>{mockMode ? 'You are using development fixtures. Manuals, camera images, and recorded speech are not analyzed; automatic checks return unable to verify.' : 'This prototype checks visible requirements. Hidden properties such as torque require human review. Physical-kit validation is still pending.'}</p></div>
    <form method="dialog"><button className="button primary">Got it<Icon name="arrow"/></button></form>
  </dialog>;
});
export default WorkflowGuide;
