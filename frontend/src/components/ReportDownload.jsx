function MiniChart({ title, items }) {
  if (!items?.length) return null;
  const max = Math.max(...items.map((item) => item.count), 1);
  return <div className="report-chart"><h4>{title}</h4>{items.map((item) => <div className="report-bar" key={item.label}><span>{item.label}</span><div><i style={{ width: `${(item.count / max) * 100}%` }} /></div><b>{item.count}</b></div>)}</div>;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[character]);
}

function metricRows(items = []) {
  return items.map((item) => `<tr><td>${escapeHtml(item.label)}</td><td>${escapeHtml(item.count)}</td></tr>`).join("");
}

function incidentTable(rows = []) {
  if (!rows.length) return "<p>No incident records matched this scope.</p>";
  const columns = Object.keys(rows[0]);
  return `<table><thead><tr>${columns.map((column) => `<th>${escapeHtml(column.replaceAll("_", " "))}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${columns.map((column) => `<td>${escapeHtml(row[column])}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}

function rootCauseNotes(notes = []) {
  if (!notes.length) return "<p>No governed root-cause notes are available for this scope.</p>";
  return notes.map((note) => `<h3>${escapeHtml(note.cause)}</h3><p><b>What it means:</b> ${escapeHtml(note.meaning)}</p><p><b>Validate:</b> ${escapeHtml(note.validate)}</p><p><b>Prevent recurrence:</b> ${escapeHtml(note.prevention)}</p>`).join("");
}

function wordDocument(report, relationshipGraph) {
  const graphNodes = relationshipGraph?.nodes || [];
  const graphEdges = relationshipGraph?.edges || [];
  const graphRows = graphEdges.map((edge) => {
    const source = graphNodes.find((node) => node.id === edge.source)?.label || edge.source;
    const target = graphNodes.find((node) => node.id === edge.target)?.label || edge.target;
    return `<tr><td>${escapeHtml(source)}</td><td>${escapeHtml(edge.relationship.replaceAll("_", " "))}</td><td>${escapeHtml(target)}</td></tr>`;
  }).join("") || "<tr><td colspan=\"3\">No recorded relationships in this report scope.</td></tr>";
  return `<!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(report.title)}</title><style>
    body{font-family:Calibri,Arial,sans-serif;color:#172033;line-height:1.45;margin:38px} h1{color:#135d8f;border-bottom:3px solid #27a5a5;padding-bottom:10px} h2{color:#135d8f;margin-top:28px} .subtitle{color:#526174}.stats{width:100%;border-collapse:separate;border-spacing:8px 0}.stats td{background:#edf7f7;padding:12px;border-radius:5px}.stats b{display:block;color:#135d8f;font-size:18px} table{width:100%;border-collapse:collapse;margin:12px 0 24px;font-size:9pt} th{background:#135d8f;color:white;text-align:left;padding:7px} td{border:1px solid #d8e1e8;padding:6px;vertical-align:top} tr:nth-child(even){background:#f5f8fa}.note{background:#fff8df;padding:10px;border-left:4px solid #d4a52a}
  </style></head><body><h1>${escapeHtml(report.title)}</h1><p class="subtitle">Generated from governed incident analytics</p><table class="stats"><tr>${(report.stats || []).map((stat) => `<td><span>${escapeHtml(stat.label)}</span><b>${escapeHtml(stat.value)}</b></td>`).join("")}</tr></table>
  <h2>Executive summary</h2><p>${escapeHtml(report.markdown?.match(/## Executive summary\n([\s\S]*?)(?=\n##|$)/)?.[1] || "").replaceAll("\n", "<br>")}</p>
  <h2>Incident evidence sample</h2>${incidentTable(report.sample_incidents)}
  <h2>Severity distribution</h2><table><tbody>${metricRows(report.severity)}</tbody></table>
  <h2>Most affected applications</h2><table><tbody>${metricRows(report.applications)}</tbody></table>
  <h2>Recurring root causes</h2><table><tbody>${metricRows(report.root_causes)}</tbody></table>
  <h2>Root-cause notes and recommended actions</h2>${rootCauseNotes(report.root_cause_notes)}
  <h2>Knowledge graph relationships</h2><table><thead><tr><th>Source</th><th>Relationship</th><th>Target</th></tr></thead><tbody>${graphRows}</tbody></table>
  <p class="note">The report includes a small, role-governed incident evidence sample. The knowledge graph maps recurring causes to affected applications and owning teams.</p></body></html>`;
}

export default function ReportDownload({ report, relationshipGraph }) {
  if (!report) return null;
  const download = () => {
    // Word opens HTML reliably, preserving the report tables and styling
    // without adding a large document-generation dependency to the browser.
    const blob = new Blob([wordDocument(report, relationshipGraph)], { type: "application/msword;charset=utf-8" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "incident-analysis-report.doc";
    link.click();
    URL.revokeObjectURL(link.href);
  };
  return <div className="report-insights">
    <div className="report-title">Report insights</div>
    <div className="report-stats">{report.stats?.map((stat) => <div key={stat.label}><span>{stat.label}</span><b>{stat.value}</b></div>)}</div>
    <div className="report-charts"><MiniChart title="Trend by month" items={report.monthly} /><MiniChart title="Incident severity" items={report.severity} /><MiniChart title="Affected applications" items={report.applications} /><MiniChart title="Recurring root causes" items={report.root_causes} /></div>
    {report.sample_incidents?.length > 0 && <div className="report-evidence"><h4>Incident evidence sample</h4><div className="report-evidence__table">{report.sample_incidents.slice(0, 5).map((incident) => <div key={incident.incident_id}><b>{incident.incident_id}</b><span>{incident.title}</span><small>{incident.status} · {incident.severity}</small></div>)}</div></div>}
    {report.root_cause_notes?.length > 0 && <div className="report-root-notes"><h4>Root-cause notes</h4>{report.root_cause_notes.slice(0, 3).map((note) => <div key={note.cause}><b>{note.cause}</b><p>{note.meaning}</p><small>Validate: {note.validate}</small><small>Prevent: {note.prevention}</small></div>)}</div>}
    <button className="btn btn--ghost report-download" onClick={download}>Download Word report</button>
  </div>;
}
