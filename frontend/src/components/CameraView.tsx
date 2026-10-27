import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react';
import { captureFrame, drawOverlay, missingZones } from '../lib/overlay';
import type { CapturedFrame, Step, VerifyResult } from '../lib/types';
import Icon from './Icon';
import { startMotionMonitor } from '../lib/motion';

export type CameraHandle = { capture: () => CapturedFrame };
type Props = {
  frame: CapturedFrame | null;
  result: VerifyResult | null;
  checkedStep?: Step;
  activeStepId?: number;
  capturedStepId?: number;
  attemptNumber?: number;
  awaitingContinue?: boolean;
  blockedReason?: string;
  showAction?: boolean;
  complete: boolean;
  checking: boolean;
  disabled: boolean;
  canCheck: boolean;
  autoEnabled?: boolean;
  onAutoToggle?: () => void;
  onAutoCheck?: () => void;
  onReady: (ready: boolean) => void;
  onCheck: () => void;
  onResume: () => void;
};

const CameraView = forwardRef<CameraHandle, Props>(function CameraView(props, ref) {
  const video = useRef<HTMLVideoElement>(null);
  const overlay = useRef<HTMLCanvasElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const generation = useRef(0);
  const mounted = useRef(false);
  const [status, setStatus] = useState<'idle' | 'requesting' | 'ready' | 'error'>('idle');
  const [error, setError] = useState<string | null>(null);
  const [maskError, setMaskError] = useState(false);
  const [motionError, setMotionError] = useState(false);
  const autoCallback = useRef(props.onAutoCheck); autoCallback.current = props.onAutoCheck;
  const cooldownUntil = useRef(-Infinity);

  function release() {
    stream.current?.getTracks().forEach(track => { track.onended = null; track.stop(); });
    stream.current = null;
    if (video.current) video.current.srcObject = null;
  }

  function stop() {
    generation.current += 1;
    release();
    setStatus('idle');
    setError(null);
    props.onReady(false);
  }

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; generation.current += 1; release(); };
  }, []);

  useImperativeHandle(ref, () => ({ capture() {
    if (!video.current || !stream.current || status !== 'ready') throw new Error('Enable the camera before checking a step.');
    return captureFrame(video.current);
  } }), [status]);

  async function start() {
    const current = ++generation.current;
    props.onReady(false);
    setStatus('requesting');
    setError(null);
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('Camera access needs a supported browser on localhost or HTTPS.');
      const acquired = await navigator.mediaDevices.getUserMedia({ audio: false, video: { width: { ideal: 640 }, height: { ideal: 480 } } });
      if (!mounted.current || current !== generation.current) { acquired.getTracks().forEach(track => track.stop()); return; }
      stream.current = acquired;
      for (const track of acquired.getVideoTracks()) track.onended = () => {
        if (!mounted.current || stream.current !== acquired) return;
        generation.current += 1;
        release();
        props.onReady(false);
        setStatus('error');
        setError('The camera disconnected. Reconnect it and enable the camera again.');
      };
      if (!video.current) throw new Error('The camera view is unavailable.');
      video.current.srcObject = acquired;
      await video.current.play();
      if (mounted.current && current === generation.current && video.current.readyState >= 2) {
        setStatus('ready'); props.onReady(true);
      }
    } catch (cause) {
      if (!mounted.current || current !== generation.current) return;
      release();
      setStatus('error');
      props.onReady(false);
      const name = cause instanceof DOMException ? cause.name : '';
      setError(name === 'NotAllowedError' ? 'Camera access was denied. Allow camera access in your browser, then try again.' :
        name === 'NotFoundError' ? 'No camera was found. Connect a webcam and try again.' :
        name === 'NotReadableError' ? 'The camera is busy. Close other camera apps and try again.' :
        cause instanceof Error ? cause.message : 'The camera could not be started. Try again.');
    }
  }

  useEffect(() => {
    let cancelled = false;
    setMaskError(false);
    if (overlay.current && props.frame) {
      void drawOverlay(overlay.current, props.result, props.checkedStep, props.frame, () => cancelled)
        .then(failed => { if (!cancelled) setMaskError(failed); })
        .catch(() => { if (!cancelled) setMaskError(true); });
    }
    return () => { cancelled = true; };
  }, [props.frame, props.result, props.checkedStep]);

  useEffect(() => {
    setMotionError(false);
    if (!props.autoEnabled || !props.canCheck || props.frame || status !== 'ready' || !video.current) return;
    return startMotionMonitor(video.current, () => {
      cooldownUntil.current = performance.now() + 2000;
      autoCallback.current?.();
    }, () => setMotionError(true), cooldownUntil.current);
  }, [props.autoEnabled, props.canCheck, props.frame, props.activeStepId, status]);

  const live = status === 'ready';
  const hasView = live || props.frame !== null;
  const unknownMissingPosition = props.result?.issues.some(issue => issue.type === 'missing') &&
    props.result.verdict !== 'unsure' && missingZones(props.result, props.checkedStep).length === 0;

  return <section className="panel camera-panel" aria-labelledby="workbench-title">
    <div className="panel-heading">
      <h2 id="workbench-title"><Icon name="crosshair" />Workbench view</h2>
      <div className="camera-source"><span className={`camera-status ${live ? 'is-live' : ''}`}><i />{props.frame ? 'CAPTURED FRAME' : live ? 'CAMERA ON' : status === 'requesting' ? 'AWAITING PERMISSION' : 'CAMERA OFF'}</span>
        <button className="button secondary small" onClick={live || status === 'requesting' ? stop : () => void start()}><Icon name={live ? 'close' : 'camera'} size={15}/>{live ? 'Stop camera' : status === 'requesting' ? 'Cancel request' : 'Enable camera'}</button>
      </div>
    </div>
    {props.showAction !== false && <div className="check-controls" aria-describedby="check-help">
      <div><span className="eyebrow">{props.complete ? 'ASSEMBLY COMPLETE' : props.activeStepId ? `STEP ${String(props.activeStepId).padStart(2, '0')}` : 'YOUR NEXT CHECK'}</span>
        <p id="check-help">{props.checking ? 'Checking the captured frame.' : props.awaitingContinue ? 'Review the result, then continue.' : props.complete ? 'All steps are complete. See the audit log for details.' : props.blockedReason || (!props.activeStepId ? 'Upload a manual to begin.' : !live ? 'Enable your camera to capture a step.' : 'Finish the step, then capture a check.')}</p></div>
      {props.frame && !props.checking && !props.awaitingContinue ? <button className="button primary" disabled={props.disabled} onClick={props.onResume}><Icon name="refresh" />{live ? 'Return to live view' : 'Clear captured frame'}</button> : !props.awaitingContinue && !props.complete && <button className="button primary" disabled={!props.canCheck} onClick={props.onCheck} aria-describedby="check-help">
        {props.checking ? <span className="spinner" /> : <Icon name="check" />} {props.checking ? 'Checking…' : `Check step${props.activeStepId ? ` ${props.activeStepId}` : ''}`}
      </button>}
    </div>}
    <div className={`camera-stage ${props.checking ? 'is-checking' : ''}`}>
      <video ref={video} autoPlay muted playsInline className={live && !props.frame ? 'visible' : ''}
        aria-label="Live workbench camera" onLoadedData={() => {
          if (stream.current && mounted.current) { setStatus('ready'); props.onReady(true); }
        }} />
      {props.frame && <>
        <img src={props.frame.dataUrl} alt={`Captured workbench frame${props.result ? ` for step ${props.result.step_id}` : ''}`} />
        <canvas ref={overlay} className="camera-overlay" aria-hidden="true" />
        <span className="frame-label">{props.checking ? 'Checking' : props.result ? 'Checked' : 'Captured'} frame · Step {props.capturedStepId ?? props.result?.step_id ?? '—'}{props.attemptNumber ? ` · Attempt ${props.attemptNumber}` : ''}</span>
      </>}
      {!hasView && <div className="camera-placeholder">
        <div className="viewfinder"><i /><i /><i /><i /><Icon name="camera" size={38} /></div>
        <h3>Your workbench goes here.</h3>
        <p>Position the camera above your assembly.<br/>Keep the whole working area in view.</p>
        <span className="placeholder-note">Camera starts only when you enable it</span>
      </div>}
      {props.result?.verdict === 'unsure' && <div className="camera-unsure"><Icon name="alert" size={15} />Unable to verify · see the written feedback</div>}
    </div>
    <div className="camera-tools"><span className="view-note">{props.frame ? 'Overlays belong to this captured frame' : 'Unmirrored overhead view'}</span><span className="view-note">{props.checking ? 'INSPECTION IN PROGRESS' : props.frame ? 'EVIDENCE HELD FOR REVIEW' : 'FIXED CAMERA / EVEN LIGHT'}</span>
    </div>
    {props.result && <dl className={`evidence-counts counts-${props.result.verdict}`} aria-label="Captured evidence counts">{Object.entries(props.result.expected_counts).map(([part, count]) => <div key={part}><dt>{part}</dt><dd><strong>{props.result!.found_counts[part] ?? '—'}</strong><span> / {count} expected</span></dd></div>)}<p>{props.result.verdict === 'unsure' ? 'Counts are unverified' : 'Detected in this frame'} · — = not established</p></dl>}
    {error && <p className="camera-error" role="alert">{error}</p>}
    {maskError && <p className="camera-note">Some mask images could not be shown. Detection boxes remain visible.</p>}
    {unknownMissingPosition && <p className="camera-note">Missing part position is not established. Follow the written fix hint.</p>}
    {props.result && <details className="inspection-details"><summary>Detection details and overlay descriptions</summary>
      <div className="camera-legend"><span><i className="legend-ok" />Consistent</span><span><i className="legend-bad" />Needs correction</span><span><i className="legend-unsure" />Unable to verify</span><span><i className="legend-missing" />Missing region</span></div>
      <ul className="overlay-descriptions">{Object.entries(props.result.expected_counts).map(([part, count]) => <li key={part}>{part}: expected {count}, detected {props.result!.found_counts[part] ?? 'not established'}.</li>)}
        {props.result.masks.map((mask, index) => <li key={index}>{mask.label}: {props.result!.verdict === 'unsure' ? 'uncertain detection' : mask.status === 'ok' ? 'consistent with requirements' : 'needs correction'}; image box {mask.box.map(n => Math.round(n)).join(', ')}.</li>)}</ul>
    </details>}
    <details className="inspection-details"><summary>Automatic motion check</summary><div className="motion-controls">
      <label><input type="checkbox" checked={props.autoEnabled ?? false} onChange={() => props.onAutoToggle?.()} />Check when motion stops</label>
      <p role="status">{!props.autoEnabled ? 'Off. Enable to check after movement settles for about 0.7 seconds.' : motionError ? 'Motion monitoring is unavailable. Use Check step, or turn monitoring off and on to retry.' : props.frame ? 'Paused on this captured frame. Resume live view to rearm.' : !props.canCheck || !live ? 'Waiting for a ready camera and current step. Monitoring pauses during other actions.' : 'Watching for movement, then stillness. Background tabs pause monitoring.'}</p>
    </div></details>
  </section>;
});

export default CameraView;
