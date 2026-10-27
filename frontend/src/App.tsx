import { useEffect, useRef, useState, type ChangeEvent } from 'react';
import AuditLog from './components/AuditLog';
import WorkflowGuide from './components/WorkflowGuide';
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
import { downloadReport } from './lib/download';
import { toVoiceWav } from './lib/audio';
import type { CapturedFrame, Health, OverrideResult, Session, VerifyResult } from './lib/types';

type Action = 'compile' | 'check' | 'override' | 'refresh' | 'voice' | 'review' | 'sample' | 'export';
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
  const [dragging, setDragging] = useState(false);
  const [reportMessage, setReportMessage] = useState('');
  const guide = useRef<HTMLDialogElement>(null);
  const history = useRef<HTMLDetailsElement>(null);
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
    if (file) await uploadFile(file);
  }

  async function uploadFile(file: File) {
    if (!backendReady) return;
    const controller = begin('compile');
    if (!controller) return;
    try {
      const id = await api.compileManual(file, controller.signal);
      if (!mounted.current || controller.signal.aborted) return;
      clearFeedback(); setVoiceMessage(''); setReportMessage('');
      setCameraReady(false); setSessionId(id); setSession(null); setManualName(file.name); setSessionFresh(false);
      await recoverSession(id, controller.signal, 'Manual compiled, but the checklist could not be loaded. ');
    } catch (cause) { if (!controller.signal.aborted) report(cause); }
    finally { finish(controller); }
  }

  async function openSample() {
    if (!backendReady || !health?.mock_mode) return;
    const controller = begin('sample');
    if (!controller) return;
    try {
      const value = await api.createSampleSession(controller.signal);
      if (!mounted.current || controller.signal.aborted) return;
      clearFeedback(); setVoiceMessage(''); setReportMessage(''); setCameraReady(false);
      setSessionId(value.session_id); setSession(value); setSessionFresh(true);
      setManualName('Sample checklist · development fixture');
    } catch (cause) { if (!controller.signal.aborted) report(cause); }
    finally { finish(controller); }
  }

  async function exportReport() {
    if (!sessionId || !sessionFresh || connection !== 'connected') return;
    const controller = begin('export');
    if (!controller) return;
    setReportMessage('');
    try {
      const value = await api.getInspectionReport(sessionId, controller.signal);
      if (mounted.current && !controller.signal.aborted) {
        downloadReport(value);
        setReportMessage('Workflow report downloaded. It identifies the provider, development fixtures, and manual overrides.');
      }
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
      const wav = await toVoiceWav(audio);
      if (!mounted.current || controller.signal.aborted || voiceContext.current !== pending) return;
      const transcript = await api.transcribe(wav, controller.signal);
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
  const blockedReason = !backendReady ? 'Reconnect the backend or check provider configuration.' : !sessionFresh ? 'Refresh the session before checking.' : awaitingContinue ? 'Review the result, then continue.' : busy ? 'Wait for the current action to finish.' : !cameraReady ? 'Enable your camera to check this step.' : frame ? 'Return to live view before another check.' : '';
  const connectionLabel = connection === 'connected' ? 'Backend connected' : connection === 'connecting' ? 'Connecting…' : 'Backend offline';
  const modeLabel = mockMode ? 'MOCK' : health ? geminiDemo ? health.model_adapters_ready ? 'GEMINI DEMO' : 'GEMINI · NOT READY' : health.model_adapters_ready ? 'META' : 'META · NOT READY' : 'MODE UNKNOWN';
  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to workspace</a>
    <header className="app-header">
      <a className="brand" href="#main-content" aria-label="StepGuard workspace"><span className="brand-mark"><Icon name="crosshair" size={22}/></span>StepGuard</a>
      <span className="header-purpose">Assembly inspection <span>One procedure. One clear next step.</span></span>
      <div className="header-actions"><button className="text-button" onClick={() => guide.current?.showModal()}><Icon name="book" size={16}/>Workflow guide</button>
        <span className="connection-label"><span className={`connection-dot ${connection}`} />{connectionLabel}</span>
        <button className="icon-button" onClick={() => setConnectionAttempt(value => value + 1)} disabled={connection === 'connecting' || busy !== null} aria-label="Check backend connection" title="Check backend connection"><Icon name="refresh" size={16}/></button>
      </div>
    </header>
    <div className="job-strip"><div className="job-source"><span className="mode-badge">{modeLabel}</span><span>{session ? manualName : 'NO PROCEDURE LOADED'}</span></div>
      <ol className="flow-stages" aria-label="Inspection stages"><li aria-current={!session ? 'step' : undefined} className={!session ? 'is-current' : 'is-done'}><span>01</span>Load</li><li aria-current={session && !reviewed ? 'step' : undefined} className={session && !reviewed ? 'is-current' : reviewed ? 'is-done' : ''}><span>02</span>Review</li><li aria-current={reviewed ? 'step' : undefined} className={reviewed ? 'is-current' : ''}><span>03</span>Inspect</li></ol>
    </div>
    <main id="main-content">
      <input type="file" accept="application/pdf,.pdf" ref={fileInput} onChange={event => void upload(event)} hidden disabled={!backendReady || busy !== null} aria-label="Assembly manual PDF" />
      {mockMode ? <div className="mode-notice"><span className="mode-badge">MOCK</span><p>Development fixtures only. Uploaded manuals, camera images, and speech are not analyzed. Automatic checks return unable to verify.</p></div> : geminiDemo && <div className="mode-notice"><span className="mode-badge">GEMINI DEMO</span><p>Gemini receives your manual, captured images, and recorded commands. Detection uses boxes. Physical-kit validation is pending.</p></div>}
      {error ? <div className="error-notice" role="alert"><Icon name="alert" /><p>{error}</p>
        <button className="button secondary" disabled={busy !== null} onClick={() => { if (connection !== 'connected') setConnectionAttempt(value => value + 1); else if (!sessionId) fileInput.current?.click(); else if (frame && !awaitingContinue) { clearFeedback(); setError(null); } else void refreshSession(); }}>{connection !== 'connected' ? 'Reconnect' : !sessionId ? 'Choose PDF' : frame && !awaitingContinue ? 'Return to live view' : 'Refresh session'}</button>
      </div> : connection === 'offline' ? <div className="notice" role="alert"><Icon name="alert" /><p>The backend is unavailable. Start it locally, then reconnect.</p><button className="button secondary" disabled={busy !== null} onClick={() => setConnectionAttempt(value => value + 1)}>Reconnect</button></div> : health && !backendReady && <div className="notice"><Icon name="alert" /><p>{geminiDemo ? 'Configure the Gemini key and model in the backend .env, then restart and reconnect.' : 'Meta access is pending. Restart the backend in mock mode to develop, or configure the Gemini demo.'}</p></div>}
      {sessionId && (!sessionFresh || activeStep?.status === 'CHECKING') && !busy && !error && connection !== 'offline' && <div className="notice"><p>{activeStep?.status === 'CHECKING' ? 'A check is still running. Refresh the session to see its result.' : 'Refresh the session before continuing.'}</p><button className="button secondary" onClick={() => void refreshSession()}>Refresh session</button></div>}


      {!session && <section className="setup-sheet" aria-labelledby="manual-title">
        <div className="setup-heading"><span className="sheet-number" aria-hidden="true">01</span><div><span className="eyebrow">PREPARE YOUR WORK ORDER</span><h1 id="manual-title">Bring the procedure.<br/>We’ll take it step by step.</h1><p>Load the assembly manual, review its requirements, then bring your workbench into view.</p></div></div>
        <div className="setup-columns"><div className="setup-input">
          <div className={`upload-zone ${dragging ? 'is-dragging' : ''} ${busy === 'compile' ? 'is-compiling' : ''}`}
            onDragOver={event => { event.preventDefault(); if (backendReady && !busy) setDragging(true); }}
            onDragLeave={event => { if (!(event.relatedTarget instanceof Node) || !event.currentTarget.contains(event.relatedTarget)) setDragging(false); }}
            onDrop={event => { event.preventDefault(); setDragging(false); if (busy || !backendReady) return; if (event.dataTransfer.files.length !== 1) { setError('Choose one PDF manual at a time.'); return; } void uploadFile(event.dataTransfer.files[0]); }}>
            <Icon name="file" size={30}/><span className="eyebrow">ASSEMBLY MANUAL / PDF</span>
            <h2>{busy === 'compile' ? 'Reading your manual…' : dragging ? 'Drop your PDF to begin' : 'Drop your procedure here'}</h2>
            <p>{busy === 'compile' ? 'Compiling requirements. This may take a moment.' : 'One PDF · up to 10 MiB'}</p>
            <button className="button primary" disabled={!backendReady || busy !== null} onClick={() => fileInput.current?.click()}>{busy === 'compile' ? <span className="spinner"/> : null}{busy === 'compile' ? 'Compiling…' : 'Choose PDF'}<Icon name="arrow" size={16}/></button>
          </div>
          {!backendReady && <p className="supporting">{connection === 'connecting' ? 'Connecting to the backend…' : 'Connect a ready backend to enable upload.'}</p>}
          {health?.mock_mode && <div className="sample-option"><span className="eyebrow">JUST EXPLORING?</span><button className="text-button" disabled={!backendReady || busy !== null} onClick={() => void openSample()}>{busy === 'sample' ? 'Opening sample…' : 'Try the sample checklist'}<Icon name="arrow" size={16}/></button><p>Development fixture · no upload or API key needed.</p></div>}
        </div><aside className="setup-notes" aria-label="Before inspection"><span className="eyebrow">AT THE BENCH</span><h2>A procedure, not a guessing game.</h2>
          <ol><li><span>01</span><div><h3>Read the requirements</h3><p>Compare every instruction, part count, and placement rule with your manual.</p></div></li><li><span>02</span><div><h3>Keep the evidence visible</h3><p>Use a fixed overhead camera and even lighting. You choose when to enable it.</p></div></li><li><span>03</span><div><h3>Review, then move forward</h3><p>A pass unlocks the next step. A correction or uncertain result keeps it locked.</p></div></li></ol>
          <button className="text-button" onClick={() => guide.current?.showModal()}>Read the workflow guide<Icon name="arrow" size={16}/></button>
        </aside></div>
      </section>}
      {session && !reviewed && <RequirementsReview key={session.session_id} checklist={session.checklist} mockMode={session.mock_mode} busy={busy === 'review'} disabled={!backendReady || !sessionFresh || busy !== null} onStart={() => void startInspection()} />}
      {session && reviewed && <div className="workbench-layout">
        <section className="current-task" aria-labelledby="task-title"><span className="task-number" aria-hidden="true">{presented ? String(presented.step_id).padStart(2, '0') : '✓'}</span><div><div className="task-title-row"><span className="eyebrow">{awaitingContinue ? 'CHECKED STEP / REVIEW THE RESULT' : session.complete ? 'ASSEMBLY COMPLETE' : `CURRENT STEP / ${session.steps.length} TOTAL`}</span></div>
          <h1 id="task-title" tabIndex={-1} ref={taskHeading}>{presented ? presented.instruction : 'Assembly complete.'}</h1>
          <p>{session.complete && !awaitingContinue ? session.steps.some(step => step.passed_via === 'override') ? 'This run includes manual overrides. Review the history for details.' : 'Every step passed an automatic check. Review the history for details.' : awaitingContinue ? 'Keep this evidence in view. Continue when you have reviewed the result.' : 'Finish this instruction, then capture a check.'}</p>
        </div></section>
        <aside className="work-order" aria-label="Procedure and current requirements"><Checklist session={session} checkingStep={checkingStep} presentedStepId={presented?.step_id}/>
          {presented && <div className="work-order-requirements"><span className="eyebrow">STEP {String(presented.step_id).padStart(2, '0')} / REQUIREMENTS</span><StepRequirements step={presented}/></div>}
          <button className="text-button history-link" onClick={() => { if (history.current) { history.current.open = true; history.current.scrollIntoView({ block: 'start' }); } }}><Icon name="history" size={16}/>View session history<Icon name="arrow" size={15}/></button>
        </aside>
        <div className="evidence-column">
          <CameraView ref={camera} frame={frame} result={result} checkedStep={checkedStep} activeStepId={presented?.step_id}
            attemptNumber={attempt?.number} capturedStepId={attempt?.stepId} awaitingContinue={awaitingContinue} blockedReason={blockedReason} showAction={false}
            complete={session.complete} checking={checkingStep !== undefined} disabled={busy !== null} canCheck={canCheck}
            autoEnabled={autoEnabled} onAutoToggle={() => setAutoEnabled(value => !value)} onAutoCheck={() => void check()}
            onReady={setCameraReady} onCheck={() => void check()} onResume={() => { if (!awaitingContinue) clearFeedback(); }}/>
          <FeedbackPanel key={sessionId ?? 'empty'} result={result} override={override} checkingStep={checkingStep} retryCount={retryCount} muted={muted} speechSupported={speechSupported} onMute={toggleMute}
            awaitingContinue={awaitingContinue} canContinue={workflow.canContinue && !busy} onContinue={continueInspection} complete={session.complete}
            actionHint={blockedReason || 'The next step stays locked until this step passes.'}
            action={!awaitingContinue && !session.complete ? frame && checkingStep === undefined ? <button className="button primary" disabled={busy !== null} onClick={clearFeedback}><Icon name="refresh"/>Return to live view</button> : <button className="button primary" disabled={!canCheck} onClick={() => void check()}>{checkingStep !== undefined ? <span className="spinner"/> : <Icon name="crosshair"/>}{checkingStep !== undefined ? 'Checking…' : `Check step ${presented?.step_id ?? ''}`}<Icon name="arrow"/></button> : undefined}
            canOverride={canAct} currentStepId={awaitingContinue ? undefined : activeStep?.step_id} busy={busy !== null} onOverride={manuallyOverride}/>
        </div>
        <div className="workbench-secondary"><details className="secondary-panel"><summary>Optional voice control</summary>
          <VoiceControl disabled={!canCheck} available={Boolean(backendReady && sessionFresh && workflow.canAct && cameraReady && !frame)} mockMode={mockMode} message={voiceMessage} onStart={startVoice} onAudio={processVoice} onCancel={cancelVoice}/>
        </details>
        <details ref={history} className="secondary-panel" id="session-history"><summary>Check and override history <span>{session.audit_log.length} events</span></summary><AuditLog entries={session.audit_log}/></details></div>
      </div>}
      {sessionId && <div className="session-footer"><span>Session {sessionId.slice(0, 8)} · {session?.complete ? 'Complete' : reviewed ? 'In progress' : 'Awaiting review'}</span>
        <div><button className="text-button" disabled={!backendReady || busy !== null} onClick={() => fileInput.current?.click()}>{busy === 'compile' ? 'Compiling…' : 'Change manual'}</button>
          <button className="text-button" disabled={connection !== 'connected' || !sessionFresh || busy !== null} onClick={() => void exportReport()}><Icon name="file" size={16}/>{busy === 'export' ? 'Exporting…' : 'Download report'}</button>
          <button className="text-button" disabled={busy !== null} onClick={() => void refreshSession()}><Icon name="refresh" size={16} />{busy === 'refresh' ? 'Refreshing…' : 'Refresh session'}</button></div>
      </div>}
      {reportMessage && <p className="report-status" role="status">{reportMessage}</p>}
      <p className="session-note">Prototype: page refresh starts a new workspace; restarting the backend clears active sessions. Upload the manual to restart. Audit snapshots are retained locally.</p>
    </main>
    <footer className="app-footer"><span><Icon name="crosshair" size={14}/>StepGuard · Automatic step checking</span><span>PROTOTYPE / LOCAL WORKSPACE</span></footer>
    <WorkflowGuide ref={guide} mockMode={mockMode}/>
  </div>;
}
