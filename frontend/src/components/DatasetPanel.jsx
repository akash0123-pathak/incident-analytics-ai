export default function DatasetPanel({ config, onRefresh, refreshing, onClearChat, canRefresh }) {
  return (
    <div className="panel-block dataset-panel">
      <div className="panel-block__label">Data workspace</div>
      <div className="dataset-panel__count">{config ? `${config.total_incidents.toLocaleString()} incident records` : "Loading dataset…"}</div>
      <p className="field-hint">Historical incident data is available for trend, severity, owner, application, and root-cause analysis.</p>
      <div className="settings-actions">
        <button className="btn btn--ghost" onClick={onRefresh} disabled={refreshing || !canRefresh} title={canRefresh ? "Refresh the local historical warehouse" : "IT Support access required"}>{refreshing ? "Refreshing…" : "Refresh warehouse"}</button>
        <button className="btn btn--ghost" onClick={onClearChat}>Clear chat</button>
      </div>
    </div>
  );
}
