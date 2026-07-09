import { useEffect, useState } from 'react';
import { AuditEntry, listHistory } from '../lib/api';

export function HistoryPanel({ sessionId }: { sessionId?: string }) {
  const [scope, setScope] = useState<'session' | 'all'>(sessionId ? 'session' : 'all');
  const [items, setItems] = useState<AuditEntry[]>([]);
  const [selected, setSelected] = useState<AuditEntry | null>(null);

  useEffect(() => {
    if (!sessionId && scope === 'session') setScope('all');
  }, [sessionId, scope]);

  async function refresh() {
    const data = await listHistory(scope === 'session' ? sessionId : undefined);
    setItems(data.items);
  }

  useEffect(() => {
    refresh().catch(() => undefined);
    const timer = window.setInterval(() => refresh().catch(() => undefined), 5000);
    return () => window.clearInterval(timer);
  }, [sessionId, scope]);

  return (
    <section className="panel history-panel">
      <div className="panel-head">
        <h2>History</h2>
        <div className="history-controls">
          <div className="segmented">
            <button
              className={scope === 'session' ? 'active' : ''}
              disabled={!sessionId}
              title={sessionId ? undefined : 'No active session yet'}
              onClick={() => setScope('session')}
            >
              This session
            </button>
            <button className={scope === 'all' ? 'active' : ''} onClick={() => setScope('all')}>
              All sessions
            </button>
          </div>
          <button className="btn-ghost" onClick={refresh}>Refresh</button>
        </div>
      </div>
      {!items.length ? (
        <p className="empty-state-text">No query history yet.</p>
      ) : (
        <div className="table-scroll">
          <table className="history-table">
            <thead>
              <tr><th>Question</th><th>Risk</th><th>Status</th><th>Duration</th><th>Rows</th><th>SQL preview</th></tr>
            </thead>
            <tbody>
              {items.map((item) => {
                const sql = item.final_sql ?? item.generated_sql ?? '';
                const status = (item.execution_status ?? 'unknown').toLowerCase();
                const risk = item.risk_level ?? (status === 'blocked' || status === 'rejected' ? 'BLOCKED' : 'UNKNOWN');
                return (
                  <tr key={item.id} className="history-row" onClick={() => setSelected(item)}>
                    <td className="cell-question" title={item.question}>{item.question}</td>
                    <td><span className={`risk risk-${risk}`}>{risk}</span></td>
                    <td><span className={`status-badge status-${status}`}>{item.execution_status ?? 'unknown'}</span></td>
                    <td>{item.execution_duration_ms != null ? `${item.execution_duration_ms} ms` : '—'}</td>
                    <td>{item.row_count ?? '—'}</td>
                    <td className="cell-sql" title={sql}><code>{sql ? `${sql.slice(0, 60)}${sql.length > 60 ? '…' : ''}` : '—'}</code></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {selected && (
        <div className="history-detail-overlay" onClick={() => setSelected(null)}>
          <div className="history-detail" onClick={(e) => e.stopPropagation()}>
            <div className="history-detail-head">
              <h3>Query detail</h3>
              <button className="btn-ghost" onClick={() => setSelected(null)}>Close</button>
            </div>
            <dl className="approval-meta">
              <div><dt>Requester</dt><dd>{selected.requester_email}</dd></div>
              <div><dt>Session</dt><dd>{selected.session_id}</dd></div>
              <div><dt>Risk</dt><dd><span className={`risk risk-${selected.risk_level ?? 'UNKNOWN'}`}>{selected.risk_level ?? 'UNKNOWN'}</span></dd></div>
              <div><dt>Status</dt><dd>{selected.execution_status ?? 'unknown'}</dd></div>
              <div><dt>Duration</dt><dd>{selected.execution_duration_ms != null ? `${selected.execution_duration_ms} ms` : '—'}</dd></div>
              <div><dt>Rows</dt><dd>{selected.row_count ?? '—'}</dd></div>
              <div><dt>Created</dt><dd>{selected.created_at}</dd></div>
            </dl>
            <label className="field-label">Question</label>
            <p>{selected.question}</p>
            <label className="field-label">Final SQL</label>
            <pre className="sql-pre"><code>{selected.final_sql ?? selected.generated_sql ?? '—'}</code></pre>
            {selected.error_message && (
              <>
                <label className="field-label">Error</label>
                <p className="error-banner">{selected.error_message}</p>
              </>
            )}
            {selected.result_summary && (
              <>
                <label className="field-label">Result summary</label>
                <p>{selected.result_summary}</p>
              </>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
