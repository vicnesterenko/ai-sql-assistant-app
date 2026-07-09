import { useEffect, useState } from 'react';
import { AuditEntry, listHistory } from '../lib/api';

export function HistoryPanel({ sessionId }: { sessionId?: string }) {
  const [items, setItems] = useState<AuditEntry[]>([]);

  async function refresh() {
    const data = await listHistory(sessionId);
    setItems(data.items);
  }

  useEffect(() => {
    refresh().catch(() => undefined);
    const timer = window.setInterval(() => refresh().catch(() => undefined), 5000);
    return () => window.clearInterval(timer);
  }, [sessionId]);

  return (
    <section className="panel history-panel">
      <div className="panel-head">
        <h2>History</h2>
        <button className="btn-ghost" onClick={refresh}>Refresh</button>
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
                const risk = item.risk_level ?? 'UNKNOWN';
                return (
                  <tr key={item.id}>
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
    </section>
  );
}
