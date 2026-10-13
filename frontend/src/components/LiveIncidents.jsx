export default function LiveIncidents({ status, feed, analysis, loading, analyzing, error, canFetch, onFetch, onAnalyze }) {
  const incidents = feed?.incidents || [];
  return <section className="live-incidents">
    <div className="live-incidents__hero">
      <div><span className="eyebrow">Read-only external feed</span><h2>Live incident intake</h2><p>Fetch the latest Jira Service Management incidents separately from the historical warehouse.</p></div>
      {canFetch && <div className="live-incidents__actions"><button className="btn btn--ghost" onClick={onFetch} disabled={loading}>{loading ? "Fetching…" : "Fetch live incidents"}</button><button className="btn btn--primary" onClick={onAnalyze} disabled={analyzing || !feed?.incidents?.length}>{analyzing ? "Analyzing…" : "Analyze live feed"}</button></div>}
    </div>
    {!canFetch && <div className="live-incidents__notice">Live incident records contain operational detail and are available to IT Support Engineers only.</div>}
    {canFetch && !status?.configured && <div className="live-incidents__notice">{status?.message || "Checking the Atlassian connection…"}</div>}
    {error && <div className="live-incidents__error">{error}</div>}
    {analysis && <section className="live-incidents__analysis"><span className="eyebrow">AI live assessment</span><p>{analysis}</p></section>}
    {canFetch && feed && <>
      <div className="live-incidents__summary">{feed.total ?? incidents.length} live incidents available from Jira Service Management</div>
      {incidents.length ? <div className="live-incidents__list">{incidents.map((incident) => <article className="live-incident" key={incident.incident_id}><div><span className="live-incident__id">{incident.incident_id}</span><h3>{incident.title}</h3><p>{incident.project || "Jira Service Management"} · {incident.type || "Incident"}</p></div><div className="live-incident__meta"><b>{incident.status || "Unknown status"}</b><span>{incident.priority || "Unprioritized"}</span><small>Updated {incident.updated_at ? new Date(incident.updated_at).toLocaleString() : "—"}</small></div></article>)}</div> : <div className="live-incidents__empty">No live incidents were returned from the configured Jira projects.</div>}
    </>}
  </section>;
}
