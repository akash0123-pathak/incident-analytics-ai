const GROUPS = [
  { id: "priority", label: "Priority", options: [["P1", "P1 priority"], ["P2", "P2 priority"], ["P3", "P3 priority"], ["P4", "P4 priority"]] },
  { id: "status", label: "Status", options: [["Open", "Open"], ["In Progress", "In Progress"], ["Resolved", "Resolved"], ["Closed", "Closed"]] },
  { id: "severity", label: "Severity", options: [["Critical", "Critical"], ["High", "High"], ["Medium", "Medium"], ["Low", "Low"]] },
  { id: "category", label: "Category", options: [["Network", "Network"], ["Server", "Infrastructure"], ["Application", "Application Error"], ["Database", "Database"], ["Security", "Security"], ["Cloud", "Infrastructure"]] },
  { id: "date", label: "Date / time", options: [["Today", "Today"], ["Last 24h", "Last 24 hours"], ["Last 7 days", "Last 7 days"], ["Last 30 days", "Last 30 days"], ["Custom", ""]] },
  { id: "resolution", label: "Resolution", options: [["Resolved", "Resolved"], ["Unresolved", "Unresolved"], ["Reopened", "Reopened"]] },
  { id: "ai", label: "AI classification", options: [["Predicted Critical", "Critical"], ["Anomaly Detected", "Critical Open"], ["Similar Incident Found", "Has recorded root cause"]] },
];

export default function CommandFilters({ selected, onChange }) {
  const toggle = (groupId, label, query) => {
    const next = { ...selected, [groupId]: selected[groupId]?.label === label ? null : { label, query } };
    onChange(next);
  };
  return <section className="command-filters-panel">
    <div className="command-filters-panel__header"><div><span className="eyebrow">INCIDENT FILTERS</span><h2>Filter the command queue</h2></div><span>Selections stay active until clicked again</span></div>
    <div className="filter-groups">
      {GROUPS.map((group) => <div className="filter-group" key={group.id}><b>{group.label}</b><div>{group.options.map(([label, query]) => <button key={label} className={selected[group.id]?.label === label ? "filter-chip filter-chip--active" : "filter-chip"} onClick={() => toggle(group.id, label, query)}>{label}</button>)}</div></div>)}
    </div>
  </section>;
}
