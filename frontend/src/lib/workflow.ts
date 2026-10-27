import type { OverrideResult, Session, VerifyResult } from './types';

// Continue acknowledges evidence in the UI. Only a server snapshot can unlock work.
export function inspectionState(session: Session | null, result: VerifyResult | null, override: OverrideResult | null, fresh: boolean) {
  const active = session?.steps.find(step => ['ACTIVE', 'FAILED', 'UNSURE', 'CHECKING'].includes(step.status));
  const acknowledgedStep = override?.step_id ?? (result?.verdict === 'pass' ? result.step_id : undefined);
  const awaitingContinue = acknowledgedStep !== undefined;
  const presentedId = acknowledgedStep ?? result?.step_id ?? active?.step_id;
  const presented = session?.checklist.steps.find(step => step.step_id === presentedId);
  const passed = session?.steps.find(step => step.step_id === acknowledgedStep);
  const reviewed = Boolean(session?.reviewed_at);
  return {
    active, presented, reviewed, awaitingContinue,
    canContinue: Boolean(fresh && reviewed && passed?.status === 'PASSED' && (session?.complete || active)),
    canAct: Boolean(fresh && reviewed && active && active.status !== 'CHECKING' && !awaitingContinue && (!result || result.step_id === active.step_id)),
  };
}
