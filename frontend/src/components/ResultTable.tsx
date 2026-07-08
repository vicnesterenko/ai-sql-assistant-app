import { useMemo, useState } from 'react';

function csvEscape(value: unknown): string {
  const text = value === null || value === undefined ? '' : String(value);
  return `"${text.replaceAll('"', '""')}"`;
}

export function ResultTable({ columns, rows }: { columns: string[]; rows: Record<string, unknown>[] }) {
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortAsc, setSortAsc] = useState(true);
  const visibleRows = useMemo(() => {
    const data = [...rows].slice(0, 100);
    if (!sortKey) return data;
    return data.sort((a, b) => {
      const av = String(a[sortKey] ?? '');
      const bv = String(b[sortKey] ?? '');
      return sortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
    });
  }, [rows, sortKey, sortAsc]);

  if (!columns.length) return null;

  if (!rows.length) {
    return (
      <div className="result-block">
        <div className="result-empty">No rows returned.</div>
      </div>
    );
  }

  function exportCsv() {
    const content = [columns.map(csvEscape).join(','), ...rows.map((row) => columns.map((col) => csvEscape(row[col])).join(','))].join('\n');
    const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'query-results.csv';
    link.click();
    URL.revokeObjectURL(url);
  }

  function sort(col: string) {
    if (sortKey === col) setSortAsc(!sortAsc);
    else {
      setSortKey(col);
      setSortAsc(true);
    }
  }

  return (
    <div className="result-block">
      <div className="table-toolbar">
        <span>{rows.length} row(s), max 100 visible</span>
        <button onClick={exportCsv}>Export CSV</button>
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>{columns.map((col) => <th key={col} onClick={() => sort(col)}>{col}{sortKey === col ? (sortAsc ? ' ↑' : ' ↓') : ''}</th>)}</tr>
          </thead>
          <tbody>
            {visibleRows.map((row, idx) => (
              <tr key={idx}>{columns.map((col) => <td key={col}>{String(row[col] ?? '')}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
