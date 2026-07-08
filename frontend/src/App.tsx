import { useState } from 'react';
import { ApprovalPanel } from './components/ApprovalPanel';
import { ChatPanel } from './components/ChatPanel';
import { HistoryPanel } from './components/HistoryPanel';
import { SchemaExplorer } from './components/SchemaExplorer';
import './styles.css';

export default function App() {
  const [email, setEmail] = useState('analyst@example.com');
  const [role, setRole] = useState<'analyst' | 'approver'>('analyst');
  const [sessionKey, setSessionKey] = useState(0);

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <h1>AI SQL Assistant</h1>
          <p>Safe natural-language analytics for internal teams</p>
        </div>
        <div className="identity">
          <label className="field">
            <span>Email</span>
            <input value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label className="field">
            <span>Role</span>
            <select value={role} onChange={(e) => setRole(e.target.value as 'analyst' | 'approver')}>
              <option value="analyst">Analyst</option>
              <option value="approver">Approver</option>
            </select>
          </label>
          <button className="btn-primary" onClick={() => setSessionKey((k) => k + 1)}>+ New session</button>
        </div>
      </header>
      <div className="layout">
        <div className="main-column">
          <ChatPanel key={sessionKey} email={email} role={role} />
        </div>
        <div className="side-column">
          <SchemaExplorer />
          <ApprovalPanel email={email} role={role} />
        </div>
      </div>
      <div className="history-section">
        <HistoryPanel />
      </div>
    </main>
  );
}
