type DiffLine = { type: 'same' | 'added' | 'removed'; text: string };

function diffLines(before: string[], after: string[]): DiffLine[] {
  const n = before.length;
  const m = after.length;
  const lcs: number[][] = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      lcs[i][j] = before[i] === after[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
    }
  }
  const result: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (before[i] === after[j]) {
      result.push({ type: 'same', text: before[i] });
      i++;
      j++;
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
      result.push({ type: 'removed', text: before[i] });
      i++;
    } else {
      result.push({ type: 'added', text: after[j] });
      j++;
    }
  }
  while (i < n) result.push({ type: 'removed', text: before[i++] });
  while (j < m) result.push({ type: 'added', text: after[j++] });
  return result;
}

export function SqlDiff({ originalSql, modifiedSql }: { originalSql: string; modifiedSql: string }) {
  const lines = diffLines(originalSql.split('\n'), modifiedSql.split('\n'));
  return (
    <div className="sql-diff">
      <div className="sql-diff-head">Approver modified this query before running it:</div>
      <pre className="sql-diff-pre">
        {lines.map((line, idx) => (
          <div key={idx} className={`sql-diff-line sql-diff-${line.type}`}>
            <span className="sql-diff-marker">{line.type === 'added' ? '+' : line.type === 'removed' ? '-' : ' '}</span>
            <code>{line.text}</code>
          </div>
        ))}
      </pre>
    </div>
  );
}
