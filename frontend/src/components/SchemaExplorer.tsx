import { useEffect, useState } from 'react';
import { getSchema, SchemaTable } from '../lib/api';

export function SchemaExplorer() {
  const [tables, setTables] = useState<SchemaTable[]>([]);
  useEffect(() => { getSchema().then((data) => setTables(data.tables)).catch(() => undefined); }, []);

  return (
    <section className="panel schema-panel">
      <div className="panel-head">
        <h2>Schema</h2>
        <span className="session-id">{tables.length} table{tables.length === 1 ? '' : 's'}</span>
      </div>
      {tables.map((table) => (
        <details key={table.name}>
          <summary>{table.name} {table.large && <span className="pill">large</span>} {table.sensitive && <span className="pill">sensitive</span>}</summary>
          <p>{table.description}</p>
          <ul>{table.columns.map((col) => <li key={col.name}><code>{col.name}</code> <small>{col.data_type}</small> — {col.description}</li>)}</ul>
        </details>
      ))}
    </section>
  );
}
