import { useEffect, useState } from 'react';
import { ApprovalItem, approveQuery, listApprovals, rejectQuery } from '../lib/api';

export function ApprovalPanel({ email, role }: { email: string; role: string }) {
  const [items, setItems] = useState<ApprovalItem[]>([]);
  const [selected, setSelected] = useState<ApprovalItem | null>(null);
  const [editedSql, setEditedSql] = useState('');
  const [rejectReason, setRejectReason] = useState('');
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    if (role !== 'approver') return;
    const data = await listApprovals(email, role);
    setItems(data.items);
    if (selected) {
      const updated = data.items.find((x) => x.id === selected.id) ?? null;
      setSelected(updated);
    }
  }

  useEffect(() => { refresh().catch((e) => setError(String(e))); }, [role]);
  useEffect(() => {
    const timer = window.setInterval(() => refresh().catch(() => undefined), 5000);
    return () => window.clearInterval(timer);
  });

  if (role !== 'approver') {
    return (
      <section className="panel approval-panel">
        <div className="panel-head"><h2>Approval queue</h2></div>
        <p className="empty-state-text">Visible only for users with the approver role.</p>
      </section>
    );
  }

  async function approve(modified: boolean) {
    if (!selected) return;
    await approveQuery(selected.id, modified ? editedSql : null, email, role);
    setSelected(null);
    await refresh();
  }

  async function reject() {
    if (!selected || !rejectReason.trim()) return;
    await rejectQuery(selected.id, rejectReason, email, role);
    setSelected(null);
    setRejectReason('');
    await refresh();
  }

  return (
    <section className="panel approval-panel">
      <div className="panel-head">
        <h2>Approval queue</h2>
        <button className="btn-ghost" onClick={refresh}>Refresh</button>
      </div>
      {error && <p className="error-banner">{error}</p>}
      {!items.length ? (
        <p className="empty-state-text">No pending approvals.</p>
      ) : (
        <div className="approval-layout">
          <div className="approval-list">
            {items.map((item) => (
              <button
                key={item.id}
                className={`approval-card ${selected?.id === item.id ? 'active' : ''}`}
                onClick={() => { setSelected(item); setEditedSql(item.generated_sql); setRejectReason(''); }}
              >
                <div className="approval-card-top">
                  <span className="requester">{item.requester_email}</span>
                  <span className={`risk risk-${item.risk_level}`}>{item.risk_level}</span>
                </div>
                <p className="approval-question">{item.original_question}</p>
              </button>
            ))}
          </div>
          {selected && (
            <div className="approval-detail">
              <h3>{selected.original_question}</h3>
              <dl className="approval-meta">
                <div>
                  <dt>Requester</dt>
                  <dd>{selected.requester_email}</dd>
                </div>
                <div>
                  <dt>Risk</dt>
                  <dd><span className={`risk risk-${selected.risk_level}`}>{selected.risk_level}</span></dd>
                </div>
              </dl>
              {selected.risk_justification && <p className="risk-justification">{selected.risk_justification}</p>}
              <label className="field-label">SQL</label>
              <textarea className="sql-editor" value={editedSql} onChange={(e) => setEditedSql(e.target.value)} />
              <div className="actions">
                <button className="btn-primary" onClick={() => approve(false)}>Approve as-is</button>
                <button className="btn-secondary" onClick={() => approve(true)}>Approve with changes</button>
              </div>
              <label className="field-label">Rejection reason</label>
              <textarea className="reject-reason" value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} placeholder="Required to reject" />
              <div className="actions">
                <button className="btn-danger" onClick={reject}>Reject</button>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
