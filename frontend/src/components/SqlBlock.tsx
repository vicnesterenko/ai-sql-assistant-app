import { useState } from 'react';

export function SqlBlock({ sql }: { sql: string }) {
  const [open, setOpen] = useState(true);
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(sql);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="sql-block">
      <div className="sql-block-head">
        <button type="button" className="sql-toggle" onClick={() => setOpen((o) => !o)}>
          <span className={`chevron ${open ? 'open' : ''}`}>▸</span> Generated SQL
        </button>
        <button type="button" className="copy-btn" onClick={copy}>{copied ? 'Copied' : 'Copy SQL'}</button>
      </div>
      {open && (
        <pre className="sql-pre"><code>{sql}</code></pre>
      )}
    </div>
  );
}
