import { useEffect, useRef, useState, type ChangeEvent } from 'react';
import AuditLog from './components/AuditLog';
import CameraView, { type CameraHandle } from './components/CameraView';
import Checklist from './components/Checklist';
import FeedbackPanel from './components/FeedbackPanel';
import Icon from './components/Icon';
import VoiceControl from './components/VoiceControl';
import RequirementsReview, { StepRequirements } from './components/Requirements';
import { inspectionState } from './lib/workflow';
import * as api from './lib/api';
import { browserSpeech, createSpeaker } from './lib/speech';
import { matchVoiceCommand } from './lib/voice';
import type { CapturedFrame, Health, OverrideResult, Session, VerifyResult } from './lib/types';

type Action = 'compile' | 'check' | 'override' | 'refresh' | 'voice' | 'review';
type Connection = 'connecting' | 'connected' | 'offline';

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [connection, setConnection] = useState<Connection>('connecting');
  const [connectionAttempt, setConnectionAttempt] = useState(0);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [sessionFresh, setSessionFresh] = useState(false);
  const [manualName, setManualName] = useState('');
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [override, setOverride] = useState<OverrideResult | null>(null);
  const [frame, setFrame] = useState<CapturedFrame | null>(null);
  const [cameraReady, setCameraReady] = useState(false);
  const [busy, setBusy] = useState<Action | null>(null);
  const [checkingStep, setCheckingStep] = useState<number | undefined>();
  const [retryCount, setRetryCount] = useState(0);
  const [attempt, setAttempt] = useState<{ stepId: number; number: number } | null>(null);
  const taskHeading = useRef<HTMLHeadingElement>(null);
  const needsFocus = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [muted, setMuted] = useState(false);
  const [speechSupported, setSpeechSupported] = useState(false);
  const [autoEnabled, setAutoEnabled] = useState(false);
  const [voiceMessage, setVoiceMessage] = useState('');
  const camera = useRef<CameraHandle>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const action = useRef<AbortController | null>(null);
  const mounted = useRef(false);
  const speech = useRef<ReturnType<typeof createSpeaker> | null>(null);
  const speechSequence = useRef(0);
  const voiceContext = useRef<{ controller: AbortController; id: string; stepId: number } | null>(null);

  useEffect(() => {
    mounted.current = true;
    speech.current = createSpeaker(browserSpeech());
    setSpeechSupported(speech.current.supported);
    return () => { mounted.current = false; action.current?.abort(); speech.current?.cancel(); };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 5000);
    let current = true;
    setConnection('connecting');
    api.getHealth(controller.signal).then(value => {
      if (current) { setHealth(value); setConnection('connected'); }
    }).catch(() => { if (current) setConnection('offline'); })
      .finally(() => window.clearTimeout(timeout));
    return () => { current = false; controller.abort(); window.clearTimeout(timeout); };
  }, [connectionAttempt]);

  useEffect(() => {
    if (!sessionId || checkingStep === undefined) return;
    const controller = new AbortController();
    let current = true;
    let timer: ReturnType<typeof setTimeout>;
    async function progress() {
      try {
        const value = await api.getSession(sessionId!, controller.signal);
        if (current) setRetryCount(value.steps.find(step => step.step_id === checkingStep)?.retry_count ?? 0);
      } catch { /* The check request owns errors and session recovery. */ }
      if (current) timer = setTimeout(() => void progress(), 1500);
    }
    timer = setTimeout(() => void progress(), 1000);
    return () => { current = false; clearTimeout(timer); controller.abort(); };
  }, [sessionId, checkingStep]);

  const mockMode = session?.mock_mode === true || health?.mock_mode === true;
  const geminiDemo = (session?.provider ?? health?.provider) === 'gemini';
  const backendReady = connection === 'connected' && health !== null && (health.mock_mode || health.model_adapters_ready);
  const workflow = inspectionState(session, result, override, sessionFresh);
  const { active: activeStep, presented, reviewed, awaitingContinue } = workflow;
  const canAct = Boolean(backendReady && workflow.canAct && !busy);
  const canCheck = canAct && cameraReady && !frame;

  useEffect(() => {
    if (reviewed && needsFocus.current) { taskHeading.current?.focus(); needsFocus.current = false; }
  }, [reviewed, presented?.step_id, awaitingContinue]);

  function clearFeedback() {
    setResult(null); setFrame(null); setOverride(null); setAttempt(null); speech.current?.cancel();
  }

  function report(cause: unknown, prefix = '') {
    if (!mounted.current) return;
    const message = cause instanceof Error ? cause.message : 'The action could not be completed. Try again.';
    if (cause instanceof api.ApiError && cause.status === 404) {
      setSession(null); setSessionId(null); setSessionFresh(false); clearFeedback();
      setError('This session is no longer available. Upload the manual to start a new one.');
    } else {
      setError(prefix + message);
      if (cause instanceof api.ApiError && cause.status === 0) setConnection('offline');
    }
  }

  function begin(kind: Action): AbortController | null {
    if (action.current) return null;
    const controller = new AbortController();
    action.current = controller;
    setBusy(kind); setError(null);
    return controller;
  }

  function finish(controller: AbortController) {
    if (action.current !== controller) return;
    action.current = null;
    if (mounted.current) { setBusy(null); setCheckingStep(undefined); }
  }

  async function loadSession(id: string, signal: AbortSignal) {
    if (!mounted.current || signal.aborted) return;
    setSessionFresh(false);
    const value = await api.getSession(id, signal);
    if (mounted.current && !signal.aborted) { setSession(value); setSessionFresh(true); }
  }

  async function recoverSession(id: string, signal: AbortSignal, prefix = '') {
    if (!mounted.current || signal.aborted) return;
    try { await loadSession(id, signal); }
    catch (cause) { if (!signal.aborted) report(cause, prefix); }
  }

  async function startInspection() {
    if (!sessionId || !sessionFresh || !backendReady) return;
    const controller = begin('review');
    if (!controller) return;
    try {
      const value = await api.reviewSession(sessionId, controller.signal);
      if (mounted.current && !controller.signal.aborted) { needsFocus.current = true; setSession(value); setSessionFresh(true); }
    } catch (cause) { if (!controller.signal.aborted) report(cause); }
    finally { finish(controller); }
  }

  function continueInspection() {
    if (!workflow.canContinue || busy) return;
    needsFocus.current = true; clearFeedback(); setVoiceMessage('');
  }

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file || !backendReady) return;
    const controller = begin('compile');
    if (!controller) return;
    try {
      const id = await api.compileManual(file, controller.signal);
      if (!mounted.current || controller.signal.aborted) return;
      clearFeedback(); setVoiceMessage('');
      setCameraReady(false); setSessionId(id); setSession(null); setManualName(file.name); setSessionFresh(false);
      await recoverSession(id, controller.signal, 'Manual compiled, but the checklist could not be loaded. ');
    } catch (cause) { if (!controller.signal.aborted) report(cause); }
    finally { finish(controller); }
  }

  async function check() {
    if (!canCheck || !sessionId || !activeStep) return;
    const id = sessionId;
    const stepId = activeStep.step_id;
    const controller = begin('check');
    if (!controller) return;
    await performCheck(id, stepId, controller);
  }

  async function performCheck(id: string, stepId: number, controller: AbortController) {
    try {
      const captured = camera.current?.capture();
      if (!captured) throw new Error('Enable your camera before checking a step.');
      clearFeedback(); setFrame(captured); setRetryCount(0); setCheckingStep(stepId);
      setAttempt({ stepId, number: (session?.audit_log.filter(entry => entry.event === 'check_started' && entry.step_id === stepId).length ?? 0) + 1 });
      const checked = await api.verifyStep(id, stepId, captured.base64, controller.signal);
      if (!mounted.current || controller.signal.aborted) return;
      setResult(checked); setCheckingStep(undefined);
      speech.current?.speak(++speechSequence.current, `${checked.message} ${checked.fix_hint}`);
      await recoverSession(id, controller.signal, 'The check completed, but session refresh failed. ');
    } catch (cause) {
      if (!controller.signal.aborted && mounted.current) {
        setCheckingStep(undefined); report(cause);
        await recoverSession(id, controller.signal);
      }
    } finally { finish(controller); }
  }

  function startVoice(): boolean {
    if (!canCheck || !sessionId || !activeStep) return false;
    const controller = begin('voice');
    if (!controller) return false;
    voiceContext.current = { controller, id: sessionId, stepId: activeStep.step_id };
    setVoiceMessage(''); speech.current?.cancel();
    return true;
  }

  function cancelVoice() {
    const pending = voiceContext.current;
    if (!pending) return;
    pending.controller.abort(); voiceContext.current = null; finish(pending.controller);
  }

  async function processVoice(audio: Blob) {
    const pending = voiceContext.current;
    if (!pending) return;
    const { controller, id, stepId } = pending;
    try {
      const transcript = await api.transcribe(audio, controller.signal);
      if (!mounted.current || controller.signal.aborted || voiceContext.current !== pending) return;
      const label = `${transcript.mock_mode ? 'MOCK transcript' : 'Heard'}: “${transcript.text || '(no speech)'}”.`;
      if (document.hidden) { setVoiceMessage(`${label} Check canceled while the tab was hidden.`); return; }
      if (!matchVoiceCommand(transcript.text)) { setVoiceMessage(`${label} No step command matched. Try again or use Check step.`); return; }
      setVoiceMessage(`${label} Command matched for current step ${stepId}.`);
      await performCheck(id, stepId, controller);
    } catch (cause) { if (!controller.signal.aborted) report(cause); }
    finally {
      if (voiceContext.current === pending) voiceContext.current = null;
      finish(controller);
    }
  }

  async function manuallyOverride(reason: string): Promise<boolean> {
    if (!canAct || !sessionId || !activeStep || !reason.trim()) return false;
    const id = sessionId;
    const controller = begin('override');
    if (!controller) return false;
    try {
      const recorded = await api.overrideStep(id, activeStep.step_id, reason, controller.signal);
      if (!mounted.current || controller.signal.aborted) return false;
      setOverride(recorded); setVoiceMessage('');
      speech.current?.speak(++speechSequence.current, `Step ${recorded.step_id} was manually overridden. ${recorded.next_step_unlocked ? 'The next step is unlocked.' : 'The session is complete.'}`);
      await recoverSession(id, controller.signal, 'The override was recorded, but session refresh failed. ');
      return true;
    } catch (cause) {
      if (!controller.signal.aborted) { report(cause); await recoverSession(id, controller.signal); }
      return false;
    } finally { finish(controller); }
  }

  async function refreshSession() {
    if (!sessionId) return;
    const controller = begin('refresh');
    if (!controller) return;
    try { await loadSession(sessionId, controller.signal); }
    catch (cause) { if (!controller.signal.aborted) report(cause); }
    finally { finish(controller); }
  }

  function toggleMute() {
    const next = !muted;
    speech.current?.setMuted(next); setMuted(next);
  }

  const checkedStep = session?.checklist.steps.find(step => step.step_id === attempt?.stepId);
  const passedCount = session?.steps.filter(step => step.status === 'PASSED').length ?? 0;
  const blockedReason = !backendReady ? 'Reconnect the backend or check provider configuration.' : !sessionFresh ? 'Refresh the session before checking.' : awaitingContinue ? 'Review the result, then continue.' : busy ? 'Wait for the current action to finish.' : !cameraReady ? 'Enable your camera to check this step.' : frame ? 'Return to live view before another check.' : '';
  const connectionLabel = connection === 'connected' ? 'Backend connected' : connection === 'connecting' ? 'Connecting…' : 'Backend offline';
  const modeLabel = mockMode ? 'MOCK' : health ? geminiDemo ? health.model_adapters_ready ? 'GEMINI DEMO' : 'GEMINI · NOT READY' : health.model_adapters_ready ? 'META' : 'META · NOT READY' : 'MODE UNKNOWN';
  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to workspace</a>
    <header className="app-header">
      <a className="brand" href="/" aria-label="StepGuard home"><span className="brand-mark"><Icon name="shield" size={27} /></span>StepGuard<span className="prototype">PROTOTYPE</span></a>
      <div className="header-status"><span className={`connection-dot ${connection}`} /><span>{connectionLabel}</span>
        <span className="mode-badge">{modeLabel}</span>
        <button className="icon-button" onClick={() => setConnectionAttempt(value => value + 1)} disabled={connection === 'connecting' || busy !== null} aria-label="Check backend connection" title="Check backend connection"><Icon name="refresh" size={18} /></button>
      </div>
    </header>
    <main id="main-content">
      <div className="page-heading"><div><span className="eyebrow">ASSEMBLY INSPECTION</span><h1>{session ? session.checklist.product : 'Start with your assembly manual.'}</h1><p>{session ? `${manualName} · ${passedCount} of ${session.steps.length} steps passed` : 'Turn your manual into a checklist, then check one step at a time.'}</p></div>
        <ol className="flow-stages" aria-label="Inspection stages"><li className={!session ? 'is-current' : ''}>1 Upload</li><li className={session && !reviewed ? 'is-current' : ''}>2 Review</li><li className={reviewed ? 'is-current' : ''}>3 Inspect</li></ol>
      </div>
      <input type="file" accept="application/pdf,.pdf" ref={fileInput} onChange={event => void upload(event)} hidden disabled={!backendReady || busy !== null} aria-label="Assembly manual PDF" />
      {mockMode ? <div className="mode-notice"><span className="mode-badge">MOCK</span><p>Development fixtures only. Uploaded manuals, camera images, and speech are not analyzed. Automatic checks return unable to verify.</p></div> : geminiDemo && <div className="mode-notice"><span className="mode-badge">GEMINI DEMO</span><p>Gemini receives your manual, captured images, and recorded commands. Detection uses boxes. Physical-kit validation is pending.</p></div>}
      {error ? <div className="error-notice" role="alert"><Icon name="alert" /><p>{error}</p>
        <button className="button secondary" disabled={busy !== null} onClick={() => { if (connection !== 'connected') setConnectionAttempt(value => value + 1); else if (!sessionId) fileInput.current?.click(); else if (frame && !awaitingContinue) { clearFeedback(); setError(null); } else void refreshSession(); }}>{connection !== 'connected' ? 'Reconnect' : !sessionId ? 'Choose PDF' : frame && !awaitingContinue ? 'Return to live view' : 'Refresh session'}</button>
      </div> : connection === 'offline' ? <div className="notice" role="alert"><Icon name="alert" /><p>The backend is unavailable. Start it locally, then reconnect.</p><button className="button secondary" disabled={busy !== null} onClick={() => setConnectionAttempt(value => value + 1)}>Reconnect</button></div> : health && !backendReady && <div className="notice"><Icon name="alert" /><p>{geminiDemo ? 'Configure the Gemini key and model in the backend .env, then restart and reconnect.' : 'Meta access is pending. Restart the backend in mock mode to develop, or configure the Gemini demo.'}</p></div>}
      {sessionId && (!sessionFresh || activeStep?.status === 'CHECKING') && !busy && !error && connection !== 'offline' && <div className="notice"><p>{activeStep?.status === 'CHECKING' ? 'A check is still running. Refresh the session to see its result.' : 'Refresh the session before continuing.'}</p><button className="button secondary" onClick={() => void refreshSession()}>Refresh session</button></div>}

      {!session && <section className="panel setup-panel" aria-labelledby="manual-title">
        <div className="setup-mark"><Icon name="upload" size={32} /></div><span className="eyebrow">01 / UPLOAD MANUAL</span>
        <h2 id="manual-title">Your procedure starts here.</h2><p>Choose an assembly PDF. Review the extracted requirements before opening the inspection workspace.</p>
        <button className="button primary" disabled={!backendReady || busy !== null} onClick={() => fileInput.current?.click()}>{busy === 'compile' ? <span className="spinner" /> : <Icon name="upload" />}{busy === 'compile' ? 'Compiling manual…' : 'Choose PDF'}</button>
        <p className="supporting">PDF · up to 10 MiB · fixed overhead camera</p>
        {!backendReady && <p className="supporting">{connection === 'connecting' ? 'Connecting to the backend…' : 'Connect a ready backend to enable upload.'}</p>}
        <div className="setup-explanation"><span>Upload your manual</span><Icon name="arrow" /><span>Review requirements</span><Icon name="arrow" /><span>Check your assembly</span></div>
      </section>}
      {session && !reviewed && <RequirementsReview key={session.session_id} checklist={session.checklist} busy={busy === 'review'} disabled={!backendReady || !sessionFresh || busy !== null} onStart={() => void startInspection()} />}

      {session && reviewed && <>
        <section className="current-task panel" aria-labelledby="task-title"><div className="task-title-row"><span className="eyebrow">{awaitingContinue ? 'CHECKED STEP' : session.complete ? 'ASSEMBLY COMPLETE' : `CURRENT STEP ${presented?.step_id ?? ''} / ${session.steps.length}`}</span><span className="task-progress">{passedCount} / {session.steps.length} passed</span></div>
          <h2 id="task-title" tabIndex={-1} ref={taskHeading}>{presented ? presented.instruction : 'Assembly complete.'}</h2>
          {presented && <StepRequirements step={presented} />}
          {session.complete && !awaitingContinue && <p>{session.steps.some(step => step.passed_via === 'override') ? 'All steps finished. This run includes manual overrides; review the history for details.' : 'Every step passed an automatic check. Review the history for details.'}</p>}
        </section>
        <div className="inspection-grid">
          <CameraView ref={camera} frame={frame} result={result} checkedStep={checkedStep} activeStepId={presented?.step_id}
            attemptNumber={attempt?.number} capturedStepId={attempt?.stepId} awaitingContinue={awaitingContinue} blockedReason={blockedReason}
            complete={session.complete} checking={checkingStep !== undefined} disabled={busy !== null} canCheck={canCheck}
            autoEnabled={autoEnabled} onAutoToggle={() => setAutoEnabled(value => !value)} onAutoCheck={() => void check()}
            onReady={setCameraReady} onCheck={() => void check()} onResume={() => { if (!awaitingContinue) clearFeedback(); }} />
          <div className="result-column"><FeedbackPanel key={sessionId ?? 'empty'} result={result} override={override} checkingStep={checkingStep} retryCount={retryCount} muted={muted} speechSupported={speechSupported} onMute={toggleMute}
            awaitingContinue={awaitingContinue} canContinue={workflow.canContinue && !busy} onContinue={continueInspection} complete={session.complete}
            canOverride={canAct} currentStepId={awaitingContinue ? undefined : activeStep?.step_id} busy={busy !== null} onOverride={manuallyOverride} />
            <Checklist session={session} checkingStep={checkingStep} presentedStepId={presented?.step_id} />
          </div>
        </div>
        <details className="panel secondary-panel"><summary>Optional voice control</summary>
          <VoiceControl disabled={!canCheck} available={Boolean(backendReady && sessionFresh && workflow.canAct && cameraReady && !frame)} mockMode={mockMode} message={voiceMessage}
            onStart={startVoice} onAudio={processVoice} onCancel={cancelVoice} />
        </details>
        <details className="panel secondary-panel"><summary>Check and override history <span>{session.audit_log.length} events</span></summary><AuditLog entries={session.audit_log} /></details>
      </>}
      {sessionId && <div className="session-footer"><span>Session {sessionId.slice(0, 8)} · {session?.complete ? 'Complete' : reviewed ? 'In progress' : 'Awaiting review'}</span>
        <div><button className="text-button" disabled={!backendReady || busy !== null} onClick={() => fileInput.current?.click()}>{busy === 'compile' ? 'Compiling…' : 'Change manual'}</button>
          <button className="text-button" disabled={busy !== null} onClick={() => void refreshSession()}><Icon name="refresh" size={16} />{busy === 'refresh' ? 'Refreshing…' : 'Refresh session'}</button></div>
      </div>}
      <p className="session-note">Prototype: page refresh starts a new workspace; restarting the backend clears active sessions. Upload the manual to restart. Audit snapshots are retained locally.</p>
    </main>
    <footer className="app-footer"><span>StepGuard / Automatic step checking</span><span>Fixed camera · One kit · Hackathon prototype</span></footer>
  </div>;
}
