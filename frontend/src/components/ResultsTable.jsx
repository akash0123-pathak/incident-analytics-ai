export default function ResultsTable({ rows }) {
  if (!rows || rows.length === 0) return null;
  const columns = Object.keys(rows[0]);

  return (
    <div className="results-table-wrap">
      <table className="results-table">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c}>{c.replace(/_/g, " ")}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={row.incident_id || i} className={`results-row--${String(row.severity || "").toLowerCase()}`}>
              {columns.map((c) => (
                <td key={c} data-col={c}>
                  {c === "severity" ? (
                    <span className={`sev sev--${String(row[c]).toLowerCase()}`}>{row[c]}</span>
                  ) : (
                    String(row[c] ?? "")
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
