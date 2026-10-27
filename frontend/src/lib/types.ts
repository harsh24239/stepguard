export type Verdict = 'pass' | 'fail' | 'unsure';
export type StepStatus = 'LOCKED' | 'ACTIVE' | 'CHECKING' | 'PASSED' | 'FAILED' | 'UNSURE';
export type Box = [number, number, number, number];
export type SpatialRule = { part: string; relation: string; target: string };
export type Step = {
  step_id: number;
  instruction: string;
  sam_prompts: string[];
  expected_counts: Record<string, number>;
  zone_anchor: string;
  spatial_rules: SpatialRule[];
  fix_hint_template: string;
};
export type Checklist = { product: string; steps: Step[] };
export type SessionStep = {
  step_id: number;
  status: StepStatus;
  passed_via: 'automatic' | 'override' | null;
  last_verdict: Verdict | null;
  retry_count?: number;
};
export type Issue = {
  type: 'missing' | 'wrong_part' | 'misplaced' | 'low_confidence';
  part: string;
  location_hint: string;
  message: string;
};
export type OverlayMask = { label: string; box: Box; status: 'ok' | 'bad'; mask_png_base64: string };
export type VerifyResult = {
  step_id: number;
  verdict: Verdict;
  confidence: number;
  found_counts: Record<string, number>;
  expected_counts: Record<string, number>;
  issues: Issue[];
  message: string;
  fix_hint: string;
  masks: OverlayMask[];
  latency_ms: number;
  next_step_unlocked: boolean;
};
export type AuditEntry = {
  timestamp: string;
  event: 'session_created' | 'requirements_reviewed' | 'step_activated' | 'check_started' | 'check_completed' | 'check_error' | 'override';
  step_id: number | null;
  details: Record<string, unknown>;
};
export type Session = {
  session_id: string;
  created_at: string;
  mock_mode: boolean;
  provider?: 'meta' | 'gemini';
  reviewed_at: string | null;
  checklist: Checklist;
  steps: SessionStep[];
  audit_log: AuditEntry[];
  complete: boolean;
};
export type Health = { status: 'ok'; mock_mode: boolean; milestone: string; model_adapters_ready: boolean; provider?: 'meta' | 'gemini' };
export type OverrideResult = {
  session_id: string;
  step_id: number;
  status: 'PASSED';
  passed_via: 'override';
  reason: string;
  next_step_unlocked: boolean;
};
export type CapturedFrame = { dataUrl: string; base64: string; width: number; height: number };
