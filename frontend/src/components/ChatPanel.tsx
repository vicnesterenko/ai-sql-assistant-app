import { useEffect, useState } from 'react';
import { AssistantResponse, createSession, getMessages, sendMessage } from '../lib/api';
import { ResultTable } from './ResultTable';
import { SqlBlock } from './SqlBlock';
import { SqlDiff } from './SqlDiff';

const EXAMPLE_QUESTIONS = [
  'How many new users signed up in April 2025, broken down by acquisition channel?',
  'Show me the top 20 merchants by transaction volume last quarter, excluding internal test accounts.',
  "What's the average loan approval time for applications submitted in Q1?",
  'Give me everything from the users table.',
  'Delete all test users from the database.',
];

function RiskBadge({ response }: { response: AssistantResponse }) {
  const status = response.execution_status;
  const level = response.risk_level ?? (status === 'blocked' || status === 'rejected' ? 'BLOCKED' : 'UNKNOWN');
  return <span className={`risk risk-${level}`} title={response.risk_justification ?? response.rejection_reason ?? ''}>{level}</span>;
}

function StatusStrip({ response }: { response: AssistantResponse }) {
  if (response.pending_approval) {
    return <div className="status-strip pending">⏳ Pending approval</div>;
  }
  if (response.rejection_reason) {
    return <div className="status-strip rejected">✕ Rejected: {response.rejection_reason}</div>;
  }
  if (response.sql) {
    return <div className="status-strip success">✓ Query executed</div>;
  }
  return null;
}

function AssistantCard({ response }: { response: AssistantResponse }) {
  return (
    <div className="assistant-card">
      <div className="response-head">
        <RiskBadge response={response} />
      </div>
      <p>{response.message}</p>
      <StatusStrip response={response} />
      {response.assumptions?.length > 0 && (
        <ul className="assumptions">{response.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
      )}
      {response.original_sql && response.sql && (
        <SqlDiff originalSql={response.original_sql} modifiedSql={response.sql} />
      )}
      {response.sql && <SqlBlock sql={response.sql} />}
      <ResultTable columns={response.columns ?? []} rows={response.rows ?? []} />
    </div>
  );
}

export function ChatPanel({
  email,
  role,
  onSessionChange,
}: {
  email: string;
  role: string;
  onSessionChange?: (sessionId: string) => void;
}) {
  const [sessionId, setSessionId] = useState<string>('');
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<{ id: string; role: string; content: string; response?: AssistantResponse | null }[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    const s = await createSession(email, role);
    setSessionId(s.session_id);
    onSessionChange?.(s.session_id);
    setMessages([]);
  }

  useEffect(() => { start().catch((e) => setError(String(e))); }, []);

  useEffect(() => {
    if (!sessionId) return;
    const timer = window.setInterval(async () => {
      const hasPending = messages.some((m) => m.response?.pending_approval);
      if (!hasPending) return;
      const data = await getMessages(sessionId, email, role);
      setMessages(data.messages);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [sessionId, messages, email, role]);

  async function submit() {
    if (!input.trim() || !sessionId) return;
    setLoading(true);
    setError(null);
    const text = input;
    setInput('');
    try {
      setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: 'user', content: text }]);
      const data = await sendMessage(sessionId, text, email, role);
      setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: 'assistant', content: data.response.message, response: data.response }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="panel chat-panel">
      <div className="panel-head">
        <h2>Chat</h2>
        <span className="session-id">Session: {sessionId || 'creating...'}</span>
      </div>
      <div className="messages">
        {messages.length === 0 && !loading && (
          <div className="empty-state">
            <span className="empty-state-icon">💬</span>
            <p>Ask a question to get started. Try one of these:</p>
            <div className="example-chips">
              {EXAMPLE_QUESTIONS.map((q) => (
                <button key={q} type="button" className="chip" onClick={() => setInput(q)}>{q}</button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`message ${m.role}`}>
            <div className="message-meta">{m.role}</div>
            {m.response ? <AssistantCard response={m.response} /> : <div className="bubble">{m.content}</div>}
          </div>
        ))}
        {loading && (
          <div className="message assistant">
            <div className="message-meta">assistant</div>
            <div className="bubble">
              <span className="typing-dots"><span></span><span></span><span></span></span>
            </div>
          </div>
        )}
      </div>
      {error && <div className="error">{error}</div>}
      <div className="composer">
        <textarea value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); }
        }} placeholder="Ask an analytics question..." />
        <button disabled={loading} onClick={submit}>{loading ? 'Sending...' : 'Send'}</button>
      </div>
    </section>
  );
}
