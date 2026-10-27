import type { Checklist, Health, InspectionReport, OverrideResult, Session, VerifyResult } from './types';
import { MAX_AUDIO_BYTES } from './voice';

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

const object = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null;
const counts = (value: unknown) => object(value) && Object.values(value).every(n => Number.isInteger(n) && Number(n) >= 0);
const sessionIdPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const verdicts = ['pass', 'fail', 'unsure'];
const statuses = ['LOCKED', 'ACTIVE', 'CHECKING', 'PASSED', 'FAILED', 'UNSURE'];
const provider = (value: unknown) => value === undefined || value === 'meta' || value === 'gemini';
const reportCounts = (value: Record<string, unknown>) => ['total_steps', 'automatic_passes', 'manual_overrides', 'completed_checks', 'check_errors']
  .every(key => Number.isInteger(value[key]) && Number(value[key]) >= 0);

function checklist(value: unknown): value is Checklist {
  return object(value) && typeof value.product === 'string' && Array.isArray(value.steps) && value.steps.length > 0 && value.steps.every(
    step => object(step) && Number.isInteger(step.step_id) && typeof step.instruction === 'string' &&
      Array.isArray(step.sam_prompts) && step.sam_prompts.every(s => typeof s === 'string') &&
      counts(step.expected_counts) && typeof step.zone_anchor === 'string' &&
      typeof step.fix_hint_template === 'string' && Array.isArray(step.spatial_rules) && step.spatial_rules.every(
        rule => object(rule) && ['part', 'relation', 'target'].every(key => typeof rule[key] === 'string')),
  );
}

function session(value: unknown): value is Session {
  return object(value) && typeof value.session_id === 'string' && sessionIdPattern.test(value.session_id) &&
    typeof value.mock_mode === 'boolean' && provider(value.provider) && (value.reviewed_at === null || typeof value.reviewed_at === 'string') && typeof value.complete === 'boolean' && typeof value.created_at === 'string' &&
    checklist(value.checklist) && Array.isArray(value.steps) && value.steps.length === value.checklist.steps.length &&
    value.steps.every((step, index) => object(step) && step.step_id === index + 1 && statuses.includes(String(step.status)) &&
      (step.retry_count === undefined || (Number.isInteger(step.retry_count) && Number(step.retry_count) >= 0)) &&
      [null, 'automatic', 'override'].includes(step.passed_via as null | string) &&
      (step.last_verdict === null || verdicts.includes(String(step.last_verdict)))) &&
    Array.isArray(value.audit_log) && value.audit_log.every(entry => object(entry) &&
      typeof entry.timestamp === 'string' && typeof entry.event === 'string' && object(entry.details));
}

function verification(value: unknown): value is VerifyResult {
  return object(value) && Number.isInteger(value.step_id) && verdicts.includes(String(value.verdict)) &&
    typeof value.confidence === 'number' && Number.isFinite(value.confidence) && value.confidence >= 0 && value.confidence <= 1 &&
    typeof value.message === 'string' && typeof value.fix_hint === 'string' && typeof value.next_step_unlocked === 'boolean' &&
    typeof value.latency_ms === 'number' && Number.isFinite(value.latency_ms) && value.latency_ms >= 0 &&
    counts(value.found_counts) && counts(value.expected_counts) && Array.isArray(value.issues) && value.issues.every(
      issue => object(issue) && ['missing', 'wrong_part', 'misplaced', 'low_confidence'].includes(String(issue.type)) &&
        ['part', 'location_hint', 'message'].every(key => typeof issue[key] === 'string')) &&
    Array.isArray(value.masks) && value.masks.every(mask => object(mask) && typeof mask.label === 'string' &&
      ['ok', 'bad'].includes(String(mask.status)) && typeof mask.mask_png_base64 === 'string' &&
      Array.isArray(mask.box) && mask.box.length === 4 && mask.box.every(n => typeof n === 'number' && Number.isFinite(n)) &&
      mask.box[0] >= 0 && mask.box[1] >= 0 && mask.box[2] > mask.box[0] && mask.box[3] > mask.box[1]);
}

async function request(path: string, init: RequestInit, signal?: AbortSignal): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, { ...init, signal, cache: 'no-store' });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new ApiError(0, 'Cannot reach the backend. Check the connection and try again.');
  }
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    let message = `Request failed (${response.status}).`;
    if (object(body)) {
      if (typeof body.detail === 'string') message = body.detail;
      else if (object(body.detail) && typeof body.detail.message === 'string') message = body.detail.message;
      else if (Array.isArray(body.detail)) message = 'The request was rejected. Check the selected file and current step.';
    }
    throw new ApiError(response.status, message);
  }
  return response;
}

async function validated<T>(response: Response, guard: (value: unknown) => value is T): Promise<T> {
  const value: unknown = await response.json().catch(() => null);
  if (!guard(value)) throw new ApiError(502, 'The backend returned an unexpected response. Refresh the session before continuing.');
  return value;
}

export async function getHealth(signal?: AbortSignal): Promise<Health> {
  return validated(await request('/health', {}, signal), (value): value is Health =>
    object(value) && value.status === 'ok' && typeof value.mock_mode === 'boolean' &&
    typeof value.milestone === 'string' && typeof value.model_adapters_ready === 'boolean' && provider(value.provider));
}

export async function compileManual(file: File, signal?: AbortSignal): Promise<string> {
  if (!file.size || file.size > 10 * 1024 * 1024) throw new ApiError(400, 'Choose a nonempty PDF of 10 MiB or smaller.');
  if (file.type !== 'application/pdf' && !(file.type === '' && file.name.toLowerCase().endsWith('.pdf'))) {
    throw new ApiError(400, 'Choose a PDF assembly manual.');
  }
  const form = new FormData();
  form.append('file', file.type ? file : new Blob([file], { type: 'application/pdf' }), file.name);
  const response = await request('/compile-manual', { method: 'POST', body: form }, signal);
  await validated(response, checklist);
  const id = response.headers.get('X-StepGuard-Session-ID');
  if (!id || !sessionIdPattern.test(id)) throw new ApiError(502, 'The manual response did not include a valid session ID. Upload the manual again.');
  return id;
}

export async function getSession(id: string, signal?: AbortSignal): Promise<Session> {
  const value = await validated(await request(`/session/${encodeURIComponent(id)}`, {}, signal), session);
  if (value.session_id !== id) throw new ApiError(502, 'The backend returned a different session. Upload the manual again.');
  return value;
}

export async function createSampleSession(signal?: AbortSignal): Promise<Session> {
  const value = await validated(await request('/sample-session', { method: 'POST' }, signal), session);
  if (!value.mock_mode || value.reviewed_at !== null || value.complete || value.steps.some((step, i) => step.status !== (i === 0 ? 'ACTIVE' : 'LOCKED'))) {
    throw new ApiError(502, 'The sample did not return a fresh development checklist.');
  }
  return value;
}

export async function getInspectionReport(id: string, signal?: AbortSignal): Promise<InspectionReport> {
  const value = await validated(await request(`/session/${encodeURIComponent(id)}/report`, {}, signal), (value): value is InspectionReport =>
    object(value) && value.format_version === 1 && typeof value.exported_at === 'string' && session(value.session) &&
    value.session.session_id === id && value.evidence_label === (value.session.mock_mode ? 'development fixtures' : 'recorded provider outcomes') &&
    Array.isArray(value.limitations) && value.limitations.every(item => typeof item === 'string') && object(value.summary) &&
    reportCounts(value.summary) &&
    value.summary.total_steps === value.session.steps.length && value.summary.complete === value.session.complete);
  return value;
}

export async function reviewSession(id: string, signal?: AbortSignal): Promise<Session> {
  const value = await validated(await request(`/session/${encodeURIComponent(id)}/review`, { method: 'POST' }, signal), session);
  if (value.session_id !== id || !value.reviewed_at) throw new ApiError(502, 'Review could not be confirmed. Refresh the session and try again.');
  return value;
}

export async function verifyStep(id: string, stepId: number, base64: string, signal?: AbortSignal): Promise<VerifyResult> {
  const value = await validated(await request('/verify-step', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: id, step_id: stepId, image_base64: base64 }) }, signal), verification);
  if (value.step_id !== stepId) throw new ApiError(502, 'The backend returned a different step. Refresh the session before continuing.');
  return value;
}

export async function overrideStep(id: string, stepId: number, reason: string, signal?: AbortSignal): Promise<OverrideResult> {
  return validated(await request('/override', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: id, step_id: stepId, reason: reason.trim() }) }, signal), (value): value is OverrideResult =>
    object(value) && value.session_id === id && value.step_id === stepId && value.status === 'PASSED' &&
    value.passed_via === 'override' && typeof value.reason === 'string' && typeof value.next_step_unlocked === 'boolean');
}

export async function transcribe(audio: Blob, signal?: AbortSignal): Promise<{ text: string; mock_mode: boolean }> {
  const mime = audio.type.split(';', 1)[0].trim().toLowerCase();
  const extension: Record<string, string> = { 'audio/webm': 'webm', 'audio/ogg': 'ogg', 'audio/mp4': 'mp4', 'audio/wav': 'wav' };
  if (!audio.size || audio.size > MAX_AUDIO_BYTES) throw new ApiError(400, 'Record a nonempty audio clip of 5 MiB or smaller.');
  if (!extension[mime]) throw new ApiError(415, 'This audio format is unsupported. Use Check step.');
  const form = new FormData(); form.append('file', audio, `command.${extension[mime]}`);
  return validated(await request('/transcribe', { method: 'POST', body: form }, signal),
    (value): value is { text: string; mock_mode: boolean } => object(value) && typeof value.text === 'string' && value.text.length <= 4000 && typeof value.mock_mode === 'boolean');
}
