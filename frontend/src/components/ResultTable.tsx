import { useEffect, useMemo, useState } from 'react';

const PAGE_SIZE = 100;

function csvEscape(value: unknown): string {
  const text = value === null || value === undefined ? '' : String(value);
  return `"${text.replaceAll('"', '""')}"`;
}

export function ResultTable({ columns, rows }: { columns: string[]; rows: Record<string, unknown>[] }) {
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortAsc, setSortAsc] = useState(true);
  const [page, setPage] = useState(0);

  const sortedRows = useMemo(() => {
    const data = [...rows];
    if (!sortKey) return data;
    return data.sort((a, b) => {
      const av = String(a[sortKey] ?? '');
      const bv = String(b[sortKey] ?? '');
      return sortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
    });
  }, [rows, sortKey, sortAsc]);

  const pageCount = Math.max(1, Math.ceil(sortedRows.length / PAGE_SIZE));

  useEffect(() => {
    setPage(0);
  }, [rows, sortKey, sortAsc]);

  const visibleRows = useMemo(
    () => sortedRows.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE),
    [sortedRows, page],
  );

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
        <span>{rows.length} row(s), max {PAGE_SIZE} per page</span>
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
      {pageCount > 1 && (
        <div className="table-pagination">
          <button disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))}>Prev</button>
          {Array.from({ length: pageCount }, (_, i) => i)
            .filter((i) => i === 0 || i === pageCount - 1 || Math.abs(i - page) <= 1)
            .reduce<number[]>((acc, i) => {
              if (acc.length && i - acc[acc.length - 1] > 1) acc.push(-1);
              acc.push(i);
              return acc;
            }, [])
            .map((i, idx) =>
              i === -1 ? (
                <span key={`gap-${idx}`} className="page-gap">…</span>
              ) : (
                <button key={i} className={i === page ? 'active' : ''} onClick={() => setPage(i)}>{i + 1}</button>
              ),
            )}
          <button disabled={page === pageCount - 1} onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}>Next</button>
        </div>
      )}
    </div>
  );
}
