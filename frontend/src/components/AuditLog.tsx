import type { AuditEntry } from '../lib/types';

function describe(entry: AuditEntry): string {
  const step = entry.step_id ? `Step ${entry.step_id}` : 'Session';
  if (entry.event === 'session_created') return 'Assembly session started';
  if (entry.event === 'requirements_reviewed') return 'Extracted requirements reviewed';
  if (entry.event === 'step_activated') return `${step} activated`;
  if (entry.event === 'check_started') return `${step} check started`;
  if (entry.event === 'check_error') return `${step} check could not complete`;
  if (entry.event === 'override') return `${step} manually overridden`;
  const result = entry.details.result;
  const verdict = result && typeof result === 'object' && 'verdict' in result ? String(result.verdict) : 'completed';
  return `${step} · ${verdict}`;
}

export default function AuditLog({ entries }: { entries: AuditEntry[] }) {
  return <section className="panel audit-panel" aria-labelledby="audit-title">
    <div className="panel-heading"><h2 id="audit-title">Audit log</h2><span className="subtle-tag">{entries.length ? `${entries.length} EVENTS` : 'NO EVENTS'}</span></div>
    {entries.length === 0 ? <p className="audit-empty">Checks, results, and manual overrides will appear here.</p> :
      <ol className="audit-list" aria-label="Session audit events, newest first">{[...entries].reverse().map((entry, index) => {
        const time = new Date(entry.timestamp);
        const validTime = Number.isFinite(time.getTime());
        return <li key={`${entry.timestamp}-${index}`} className={entry.event === 'override' ? 'audit-override' : ''}>
          <span className="audit-dot" /><div><span className="audit-description">{describe(entry)}</span>
            {entry.event === 'override' && typeof entry.details.reason === 'string' && <p>{entry.details.reason}</p>}
          </div><time dateTime={entry.timestamp} title={entry.timestamp}>{validTime ? time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—'}</time>
        </li>;
      })}</ol>}
  </section>;
}
