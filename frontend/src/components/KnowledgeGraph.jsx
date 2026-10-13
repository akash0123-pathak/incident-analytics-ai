const KIND_LABELS = { root_cause: "Root cause", incident: "Incident", application: "Application", team: "Team" };

function shortLabel(label, max = 22) {
  return label.length > max ? `${label.slice(0, max - 1)}…` : label;
}

function arrange(nodes, width) {
  const hasIncidents = nodes.some((node) => node.kind === "incident");
  const lanes = hasIncidents
    ? { root_cause: 120, incident: 380, application: 640, team: 870 }
    : { root_cause: 150, application: 490, team: 820 };
  const grouped = nodes.reduce((all, node) => ({ ...all, [node.kind]: [...(all[node.kind] || []), node] }), {});
  const tallestLane = Math.max(...Object.values(grouped).map((group) => group.length), 1);
  const positioned = Object.entries(grouped).flatMap(([kind, group]) => group.map((node, index) => ({
    ...node,
    x: lanes[kind] || width / 2,
    y: 58 + index * 64,
  })));
  return { positioned, height: Math.max(220, tallestLane * 64 + 88) };
}

export default function KnowledgeGraph({ topology }) {
  const nodes = topology?.nodes || [];
  const edges = topology?.edges || [];
  const scope = topology?.scope;
  const visibleKinds = Object.keys(KIND_LABELS).filter((kind) => nodes.some((node) => node.kind === kind));
  if (!nodes.length) return <section className="chart-card graph-view"><h3>Knowledge graph topology</h3><p className="field-hint">No recorded root-cause relationships exist in this query’s incident set.</p></section>;
  const width = 980;
  const { positioned, height } = arrange(nodes, width);
  const lookup = Object.fromEntries(positioned.map((node) => [node.id, node]));
  return <section className="chart-card graph-view">
    <div className="graph-heading"><div><h3>{scope?.view === "recurrence" ? "Recurring incident impact map" : "Knowledge graph topology"}</h3><p className="field-hint">{scope?.description || (scope?.is_query_scoped ? "Relationships for the incidents matched by this query." : "Incidents connect to root causes, affected applications, and owning teams.")}</p></div>{scope?.is_query_scoped && <span className="graph-scope">{scope.incident_count} linked</span>}</div>
    <svg className="graph-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Incident relationship knowledge graph">
      <title>Incident relationship knowledge graph</title>
      {edges.map((edge, index) => { const source = lookup[edge.source]; const target = lookup[edge.target]; return source && target ? <line key={`${edge.source}-${edge.target}-${index}`} x1={source.x} y1={source.y} x2={target.x} y2={target.y} className="graph-edge" /> : null; })}
      {positioned.map((node) => <g key={node.id} className={`graph-node graph-node--${node.kind} graph-node--${String(node.severity || "").toLowerCase()}`}>
        <rect x={node.x - 94} y={node.y - 21} width="188" height="42" rx="11" />
        <text x={node.x} y={node.y + 4} textAnchor="middle">{shortLabel(node.label, node.kind === "incident" ? 13 : 21)}</text>
        <title>{`${KIND_LABELS[node.kind]}: ${node.label}${node.severity ? ` (${node.severity})` : ""}`}</title>
      </g>)}
      {visibleKinds.map((kind) => <text key={kind} x={scope?.view === "recurrence" ? ({ root_cause: 150, application: 490, team: 820 })[kind] : ({ root_cause: 120, incident: 380, application: 640, team: 870 })[kind]} y="22" textAnchor="middle" className="graph-lane-label">{KIND_LABELS[kind]}s</text>)}
    </svg>
    {scope?.view !== "recurrence" && <div className="graph-legend"><span><i className="graph-dot graph-dot--critical" />Critical incident</span><span><i className="graph-dot graph-dot--high" />High incident</span><span><i className="graph-dot graph-dot--medium" />Medium incident</span><span><i className="graph-dot graph-dot--low" />Low incident</span></div>}
  </section>;
}
