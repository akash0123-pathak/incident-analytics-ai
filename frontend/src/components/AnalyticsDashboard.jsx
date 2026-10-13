import React, { useState } from "react";
import {
  IconTrendingUp,
  IconCalendar,
  IconAlertTriangle,
  IconCheckCircle,
  IconClock,
  IconArrowUpRight,
  IconSearch,
  IconSparkles,
  IconX,
} from "./Icons.jsx";
import KnowledgeGraph from "./KnowledgeGraph.jsx";

// Severity color mapping
const SEVERITY_COLORS = {
  critical: "#ef4444",
  high: "#f97316",
  medium: "#eab308",
  low: "#10b981",
};

// SVG Area Chart for Daily / Weekly / Monthly trends
function TrendAreaChart({ items = [], granularity, onGranularityChange, onAsk }) {
  const [hoverIndex, setHoverIndex] = useState(null);

  if (!items || items.length === 0) {
    return (
      <div className="chart-empty-state">
        <p>No trend data available for this timeframe.</p>
      </div>
    );
  }

  const maxVal = Math.max(...items.map((d) => d.count), 1);
  const minVal = 0;
  const totalCount = items.reduce((acc, curr) => acc + curr.count, 0);
  const avgCount = Math.round(totalCount / items.length);
  const peakItem = items.reduce((prev, current) => (current.count > prev.count ? current : prev), items[0]);

  // Dimensions
  const width = 760;
  const height = 220;
  const padL = 45;
  const padR = 25;
  const padT = 25;
  const padB = 35;
  const chartW = width - padL - padR;
  const chartH = height - padT - padB;

  // Calculate coordinates
  const points = items.map((item, index) => {
    const x = padL + (index / (items.length - 1 || 1)) * chartW;
    const y = padT + chartH - ((item.count - minVal) / (maxVal - minVal || 1)) * chartH;
    return { x, y, item, index };
  });

  // Generate smooth SVG path
  let pathD = "";
  if (points.length > 0) {
    pathD = `M ${points[0].x} ${points[0].y}`;
    for (let i = 0; i < points.length - 1; i++) {
      const p0 = points[i === 0 ? 0 : i - 1];
      const p1 = points[i];
      const p2 = points[i + 1];
      const p3 = points[i + 2] || p2;

      const cp1x = p1.x + (p2.x - p0.x) / 6;
      const cp1y = p1.y + (p2.y - p0.y) / 6;
      const cp2x = p2.x - (p3.x - p1.x) / 6;
      const cp2y = p2.y - (p3.y - p1.y) / 6;

      pathD += ` C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${p2.x} ${p2.y}`;
    }
  }

  // Area closing path
  const areaD = `${pathD} L ${points[points.length - 1].x} ${padT + chartH} L ${points[0].x} ${padT + chartH} Z`;

  const hoveredPoint = hoverIndex !== null ? points[hoverIndex] : null;

  const handleMouseMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const mouseX = ((e.clientX - rect.left) / rect.width) * width;
    
    // Find closest point
    let closestIdx = 0;
    let closestDist = Infinity;
    points.forEach((p, idx) => {
      const dist = Math.abs(p.x - mouseX);
      if (dist < closestDist) {
        closestDist = dist;
        closestIdx = idx;
      }
    });
    setHoverIndex(closestIdx);
  };

  const handleMouseLeave = () => {
    setHoverIndex(null);
  };

  return (
    <section className="analytics-card trend-card">
      <div className="trend-card__header">
        <div>
          <div className="trend-card__title-row">
            <IconTrendingUp size={20} className="text-blue" />
            <h3 className="card-title">Incident Trend Velocity</h3>
          </div>
          <p className="card-sub">
            Continuous operational volume over time. Hover over data points to inspect intervals.
          </p>
        </div>

        <div className="trend-card__controls">
          <div className="granularity-toggle" role="group" aria-label="Timeframe">
            <button
              className={`toggle-btn ${granularity === "day" ? "toggle-btn--active" : ""}`}
              onClick={() => onGranularityChange("day")}
            >
              Daily (30d)
            </button>
            <button
              className={`toggle-btn ${granularity === "week" ? "toggle-btn--active" : ""}`}
              onClick={() => onGranularityChange("week")}
            >
              Weekly (12w)
            </button>
            <button
              className={`toggle-btn ${granularity === "month" ? "toggle-btn--active" : ""}`}
              onClick={() => onGranularityChange("month")}
            >
              Monthly (12m)
            </button>
          </div>

          <button
            className="btn btn--ghost btn--sm"
            onClick={() => onAsk(`What caused the peak in incident volume around ${peakItem?.label}?`)}
            title="Ask about the peak trend"
          >
            Ask about peak <IconArrowUpRight size={14} />
          </button>
        </div>
      </div>

      <div className="trend-summary-pills">
        <div className="summary-pill">
          <span>Interval Average</span>
          <b>{avgCount} incidents</b>
        </div>
        <div className="summary-pill">
          <span>Peak Interval</span>
          <b>{peakItem.count} ({peakItem.label})</b>
        </div>
        <div className="summary-pill">
          <span>Total in View</span>
          <b>{totalCount.toLocaleString()} incidents</b>
        </div>
      </div>

      <div className="svg-chart-container" onMouseMove={handleMouseMove} onMouseLeave={handleMouseLeave}>
        <svg viewBox={`0 0 ${width} ${height}`} className="trend-svg" preserveAspectRatio="none">
          <defs>
            <linearGradient id="trendGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#2563eb" stopOpacity="0.32" />
              <stop offset="100%" stopColor="#2563eb" stopOpacity="0.01" />
            </linearGradient>
          </defs>

          {/* Grid lines */}
          {[0, 0.25, 0.5, 0.75, 1].map((ratio, idx) => {
            const y = padT + chartH * (1 - ratio);
            const val = Math.round(minVal + (maxVal - minVal) * ratio);
            return (
              <g key={`grid-${idx}`}>
                <line x1={padL} y1={y} x2={width - padR} y2={y} stroke="#e2e8f0" strokeDasharray="3 3" />
                <text x={padL - 8} y={y + 3} textAnchor="end" className="chart-axis-label">
                  {val}
                </text>
              </g>
            );
          })}

          {/* Area Fill */}
          <path d={areaD} fill="url(#trendGradient)" />

          {/* Line Stroke */}
          <path d={pathD} fill="none" stroke="#2563eb" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />

          {/* X Axis Date Labels */}
          {points.map((p, i) => {
            // Show every nth label to prevent clutter
            const step = items.length > 20 ? 4 : items.length > 10 ? 2 : 1;
            if (i % step !== 0 && i !== points.length - 1) return null;
            return (
              <text key={`xlabel-${i}`} x={p.x} y={height - 10} textAnchor="middle" className="chart-axis-label">
                {p.item.label.length > 7 ? p.item.label.slice(5) : p.item.label}
              </text>
            );
          })}

          {/* Hover Crosshair and Dot */}
          {hoveredPoint && (
            <g className="chart-hover-group">
              <line
                x1={hoveredPoint.x}
                y1={padT}
                x2={hoveredPoint.x}
                y2={padT + chartH}
                stroke="#3b82f6"
                strokeWidth="1.5"
                strokeDasharray="4 4"
              />
              <circle cx={hoveredPoint.x} cy={hoveredPoint.y} r="6" fill="#ffffff" stroke="#2563eb" strokeWidth="3" />
            </g>
          )}
        </svg>

        {/* Floating Tooltip */}
        {hoveredPoint && (
          <div
            className="chart-tooltip"
            style={{
              left: `${(hoveredPoint.x / width) * 100}%`,
              top: `${(hoveredPoint.y / height) * 100}%`,
            }}
          >
            <div className="tooltip-date">{hoveredPoint.item.label}</div>
            <div className="tooltip-count">
              <b>{hoveredPoint.item.count}</b> incidents
            </div>
            <div className="tooltip-share">
              {Math.round((hoveredPoint.item.count / maxVal) * 100)}% of peak
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

// Interactive SVG Donut Chart for Severity Breakdown
function SeverityDonutChart({ items = [] }) {
  const [hoveredSev, setHoveredSev] = useState(null);
  const total = items.reduce((sum, d) => sum + d.count, 0) || 1;

  const size = 180;
  const strokeWidth = 22;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;

  let accumulated = 0;
  const slices = items.map((item) => {
    const key = String(item.label).toLowerCase();
    const color = SEVERITY_COLORS[key] || "#94a3b8";
    const percentage = item.count / total;
    const strokeDasharray = `${percentage * circumference} ${circumference}`;
    const strokeDashoffset = -accumulated * circumference;
    accumulated += percentage;
    return { ...item, key, color, percentage, strokeDasharray, strokeDashoffset };
  });

  const activeItem = hoveredSev ? items.find((s) => String(s.label).toLowerCase() === hoveredSev) : null;

  return (
    <section className="analytics-card">
      <div className="card-header-compact">
        <h3 className="card-title">Severity Breakdown</h3>
        <span className="badge-tag">Operational Impact</span>
      </div>

      <div className="donut-container">
        <div className="donut-svg-wrap">
          <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="donut-svg">
            <circle
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="transparent"
              stroke="#f1f5f9"
              strokeWidth={strokeWidth}
            />
            {slices.map((slice) => (
              <circle
                key={slice.key}
                cx={size / 2}
                cy={size / 2}
                r={radius}
                fill="transparent"
                stroke={slice.color}
                strokeWidth={hoveredSev === slice.key ? strokeWidth + 4 : strokeWidth}
                strokeDasharray={slice.strokeDasharray}
                strokeDashoffset={slice.strokeDashoffset}
                strokeLinecap="round"
                className="donut-segment"
                onMouseEnter={() => setHoveredSev(slice.key)}
                onMouseLeave={() => setHoveredSev(null)}
              />
            ))}
          </svg>
          <div className="donut-center-label">
            <strong>{activeItem ? activeItem.count : total.toLocaleString()}</strong>
            <small>{activeItem ? activeItem.label : "Total Records"}</small>
          </div>
        </div>

        <div className="donut-legend">
          {slices.map((slice) => (
            <div
              key={slice.key}
              className={`donut-legend-row ${hoveredSev === slice.key ? "donut-legend-row--active" : ""}`}
              onMouseEnter={() => setHoveredSev(slice.key)}
              onMouseLeave={() => setHoveredSev(null)}
            >
              <div className="legend-label-group">
                <span className="legend-dot" style={{ backgroundColor: slice.color }} />
                <span className="legend-name">{slice.label}</span>
              </div>
              <div className="legend-value-group">
                <b>{slice.count}</b>
                <span className="legend-percent">({Math.round(slice.percentage * 100)}%)</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// Status Lifecycle Progress Bar
function StatusLifecycle({ items = [] }) {
  const total = items.reduce((sum, d) => sum + d.count, 0) || 1;
  const statusColors = {
    closed: "#1e3a8a",
    resolved: "#10b981",
    "in progress": "#f59e0b",
    open: "#ef4444",
  };

  return (
    <section className="analytics-card">
      <div className="card-header-compact">
        <h3 className="card-title">Incident Lifecycle</h3>
        <span className="badge-tag">Queue State</span>
      </div>

      <div className="lifecycle-bar-container">
        <div className="segmented-bar">
          {items.map((item) => {
            const key = String(item.label).toLowerCase();
            const pct = (item.count / total) * 100;
            return (
              <div
                key={item.label}
                className="segmented-bar__chunk"
                style={{
                  width: `${pct}%`,
                  backgroundColor: statusColors[key] || "#94a3b8",
                }}
                title={`${item.label}: ${item.count} (${pct.toFixed(1)}%)`}
              />
            );
          })}
        </div>

        <div className="lifecycle-grid">
          {items.map((item) => {
            const key = String(item.label).toLowerCase();
            const pct = ((item.count / total) * 100).toFixed(1);
            return (
              <div key={item.label} className="lifecycle-tile">
                <div className="lifecycle-tile__dot" style={{ backgroundColor: statusColors[key] || "#94a3b8" }} />
                <div>
                  <span className="lifecycle-tile__label">{item.label}</span>
                  <b className="lifecycle-tile__count">{item.count}</b>
                  <small className="lifecycle-tile__pct">{pct}%</small>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

// Clean Service Hotspots Leaderboard
function ServiceHotspots({ items = [], onAsk }) {
  const max = Math.max(...items.map((d) => d.count), 1);

  return (
    <section className="analytics-card">
      <div className="card-header-compact">
        <div>
          <h3 className="card-title">Service Risk Hotspots</h3>
          <p className="card-sub">Applications with the highest historical incident volume</p>
        </div>
      </div>

      <div className="hotspot-list">
        {items.slice(0, 6).map((item, idx) => {
          const pct = Math.round((item.count / max) * 100);
          return (
            <div key={item.label} className="hotspot-row">
              <div className="hotspot-rank">#{idx + 1}</div>
              <div className="hotspot-details">
                <div className="hotspot-title-row">
                  <span className="hotspot-name">{item.label}</span>
                  <b className="hotspot-count">{item.count} incidents</b>
                </div>
                <div className="hotspot-bar-track">
                  <div className="hotspot-bar-fill" style={{ width: `${pct}%` }} />
                </div>
              </div>
              <button
                className="btn-icon-drill"
                onClick={() => onAsk(`Show critical incidents affecting ${item.label} and their root causes.`)}
                title={`Investigate ${item.label}`}
              >
                <IconArrowUpRight size={14} />
              </button>
            </div>
          );
        })}
      </div>
    </section>
  );
}

// Team Workload Card
function TeamWorkload({ items = [], onAsk }) {
  const max = Math.max(...items.map((d) => d.count), 1);

  return (
    <section className="analytics-card">
      <div className="card-header-compact">
        <div>
          <h3 className="card-title">Team Workload Distribution</h3>
          <p className="card-sub">Assigned incident resolution queues across engineering teams</p>
        </div>
      </div>

      <div className="hotspot-list">
        {items.slice(0, 6).map((item) => {
          const pct = Math.round((item.count / max) * 100);
          return (
            <div key={item.label} className="hotspot-row">
              <div className="hotspot-details">
                <div className="hotspot-title-row">
                  <span className="hotspot-name">{item.label}</span>
                  <b className="hotspot-count">{item.count}</b>
                </div>
                <div className="hotspot-bar-track">
                  <div className="hotspot-bar-fill hotspot-bar-fill--blue" style={{ width: `${pct}%` }} />
                </div>
              </div>
              <button
                className="btn-icon-drill"
                onClick={() => onAsk(`Show open incidents assigned to ${item.label}.`)}
                title={`Investigate ${item.label} queue`}
              >
                <IconArrowUpRight size={14} />
              </button>
            </div>
          );
        })}
      </div>
    </section>
  );
}

// Recurring Root Causes Card
function RecurringRootCauses({ items = [], onAsk }) {
  return (
    <section className="analytics-card">
      <div className="card-header-compact">
        <div>
          <h3 className="card-title">Recurring Root Causes</h3>
          <p className="card-sub">Top patterns requiring engineering remediation</p>
        </div>
      </div>

      <div className="root-cause-grid">
        {items.slice(0, 5).map((item) => (
          <div key={item.label} className="root-cause-tile">
            <div className="root-cause-tile__header">
              <span className="root-cause-tile__name" title={item.label}>
                {item.label}
              </span>
              <span className="root-cause-tile__count">{item.count} cases</span>
            </div>
            <div className="root-cause-tile__action">
              <button
                className="btn-link"
                onClick={() => onAsk(`What incidents were caused by ${item.label} and how to prevent it?`)}
              >
                View playbooks & blast radius &rarr;
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function OperationalCharts({ volume = [], breaches = [], onAsk }) {
  const maxVolume = Math.max(...volume.map((item) => item.total), 1);
  const maxBreach = Math.max(...breaches.map((item) => item.count), 1);
  return <div className="analytics-dual-grid">
    <section className="analytics-card compact-chart-card">
      <div className="card-header-compact"><div><h3 className="card-title">Historical trends & trajectory</h3><p className="card-sub">Total daily incidents compared with critical incidents</p></div><span className="chart-legend"><i className="legend-total" /> Total <i className="legend-critical" /> Critical</span></div>
      <div className="mini-line-chart">
        <svg viewBox="0 0 640 190" preserveAspectRatio="none">
          {[.25, .5, .75, 1].map((line) => <line key={line} x1="0" x2="640" y1={190 - line * 160} y2={190 - line * 160} className="mini-grid" />)}
          <polyline className="total-line" points={volume.map((item, index) => `${index * (640 / Math.max(volume.length - 1, 1))},${180 - item.total / maxVolume * 160}`).join(" ")} />
          <polyline className="critical-line" points={volume.map((item, index) => `${index * (640 / Math.max(volume.length - 1, 1))},${180 - item.critical / maxVolume * 160}`).join(" ")} />
        </svg>
      </div>
      <button className="btn-link" onClick={() => onAsk("Show the trend of critical and total incidents over the last 30 days.")}>Investigate trend peak →</button>
    </section>
    <section className="analytics-card compact-chart-card">
      <div className="card-header-compact"><div><h3 className="card-title">SLA breaches progression</h3><p className="card-sub">Daily incidents resolved beyond the 24-hour operating threshold</p></div><span className="badge-tag">Daily breached volume</span></div>
      <div className="mini-bar-chart">{breaches.map((item) => <div className="mini-bar" key={item.label} title={`${item.label}: ${item.count} SLA breaches`}><i style={{ height: `${Math.max(item.count / maxBreach * 100, item.count ? 4 : 0)}%` }} /><span>{item.label.slice(5)}</span></div>)}</div>
      <button className="btn-link" onClick={() => onAsk("List incidents that breached the 24 hour resolution SLA and identify owners.")}>Investigate SLA breaches →</button>
    </section>
  </div>;
}

function ReportsHub({ analytics, onAsk }) {
  const downloadCsv = () => {
    const rows = [["Metric", "Value"], ["Total incidents", analytics.total_incidents], ["Open incidents", analytics.open_incidents], ["Critical incidents", analytics.critical_incidents], ["Resolved incidents", analytics.resolved_incidents], ["Average resolution hours", analytics.average_resolution_hours], [], ["Application", "Incident count"], ...analytics.incidents_by_application.map((item) => [item.label, item.count])];
    const csv = rows.map((row) => row.map((value) => `"${String(value ?? "").replaceAll('"', '""')}"`).join(",")).join("\n");
    const link = document.createElement("a"); link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" })); link.download = "incident-analytics-dashboard.csv"; link.click(); URL.revokeObjectURL(link.href);
  };
  return <section className="analytics-card reports-hub"><div><span className="eyebrow">REPORTS HUB</span><h3 className="card-title">Executive reporting & export</h3><p className="card-sub">Create a governed report or download the current analytics summary.</p></div><div className="reports-hub__actions"><button className="btn btn--primary" onClick={() => onAsk("Generate an executive incident report for the last 90 days with KPI statistics, affected applications, and recurring root causes.")}>Generate executive report</button><button className="btn btn--ghost" onClick={downloadCsv}>Download dashboard CSV</button></div></section>;
}

export default function AnalyticsDashboard({ analytics, graphTopology, onAsk, loading, activeRole }) {
  const [question, setQuestion] = useState("");
  const [granularity, setGranularity] = useState("month");

  const submit = () => {
    if (question.trim() && !loading) {
      onAsk(question.trim());
      setQuestion("");
    }
  };

  if (!analytics) {
    return (
      <div className="analytics-loading-state">
        <div className="spinner" />
        <p>Calculating live incident warehouse metrics…</p>
      </div>
    );
  }

  // Choose trend series based on granularity selection
  let trendSeries = analytics.incidents_by_month || [];
  if (granularity === "day" && analytics.incidents_by_day?.length) {
    trendSeries = analytics.incidents_by_day;
  } else if (granularity === "week" && analytics.incidents_by_week?.length) {
    trendSeries = analytics.incidents_by_week;
  }

  return (
    <div className="analytics-workspace">
      {/* Search / AI Query Banner */}
      <div className="analytics-query-card">
        <div className="analytics-query-bar">
          <div className="query-input-wrap">
            <IconSearch size={18} className="query-search-icon" />
            <input
              className="query-input"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submit()}
              placeholder="Ask anything about operational trends (e.g. Compare critical incident MTTR between Q1 and Q2)…"
            />
            {question.trim() && (
              <button
                type="button"
                className="input-clear-btn"
                onClick={() => setQuestion("")}
                title="Clear input"
              >
                <IconX size={14} />
              </button>
            )}
          </div>
          <button
            className="btn btn--primary analytics-ask-btn"
            onClick={submit}
            disabled={loading || !question.trim()}
          >
            <IconSparkles size={16} />
            <span>Ask analytics</span>
            <span className="shortcut-badge">↵</span>
          </button>
        </div>

        <div className="analytics-quick-chips">
          <span className="quick-tags-label">Quick Inquiries:</span>
          {[
            { label: "📄 Executive Monthly Report", prompt: "Generate an executive report for incidents over the last 90 days." },
            { label: "📈 Explain Trend Peak", prompt: "What drove the peak incident volume in the latest monthly period?" },
            { label: "🚨 Critical Risk by Team", prompt: "Which team owns the most critical unresolved incidents?" },
            { label: "🕸️ Root Cause Topology", prompt: "Identify recurring root causes and map their blast radius across services." },
          ].map((chip) => (
            <button
              key={chip.label}
              className="quick-tag-chip"
              onClick={() => onAsk(chip.prompt)}
              disabled={loading}
              title={`Ask: "${chip.prompt}"`}
            >
              {chip.label}
            </button>
          ))}
        </div>
      </div>

      {/* SECTION 1: Key Performance Metrics */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-icon-wrap kpi-icon-wrap--blue">
            <IconCalendar size={20} />
          </div>
          <div>
            <span className="kpi-label">Total Indexed Incidents</span>
            <strong className="kpi-value">{analytics.total_incidents.toLocaleString()}</strong>
            <span className="kpi-sub">Full historical scope</span>
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-icon-wrap kpi-icon-wrap--amber">
            <IconClock size={20} />
          </div>
          <div>
            <span className="kpi-label">Active Open Queue</span>
            <strong className="kpi-value">{analytics.open_incidents.toLocaleString()}</strong>
            <span className="kpi-sub">
              {((analytics.open_incidents / analytics.total_incidents) * 100).toFixed(1)}% of total queue
            </span>
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-icon-wrap kpi-icon-wrap--crimson">
            <IconAlertTriangle size={20} />
          </div>
          <div>
            <span className="kpi-label">Critical Severity</span>
            <strong className="kpi-value">{analytics.critical_incidents.toLocaleString()}</strong>
            <span className="kpi-sub">Highest business impact</span>
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-icon-wrap kpi-icon-wrap--emerald">
            <IconCheckCircle size={20} />
          </div>
          <div>
            <span className="kpi-label">Average Resolution MTTR</span>
            <strong className="kpi-value">{analytics.average_resolution_hours}h</strong>
            <span className="kpi-sub">{analytics.resolved_incidents.toLocaleString()} resolved / closed</span>
          </div>
        </div>
      </div>

      {/* SECTION 2: Hero Trend Velocity Area Chart (Daily / Weekly / Monthly) */}
      <TrendAreaChart
        items={trendSeries}
        granularity={granularity}
        onGranularityChange={setGranularity}
        onAsk={onAsk}
      />

      <OperationalCharts volume={analytics.volume_vs_critical_by_day} breaches={analytics.sla_breaches_by_day} onAsk={onAsk} />

      <ReportsHub analytics={analytics} onAsk={onAsk} />

      {/* SECTION 3: Distribution Grids (Severity Donut + Status Lifecycle) */}
      <div className="analytics-dual-grid">
        <SeverityDonutChart items={analytics.incidents_by_severity} />
        <StatusLifecycle items={analytics.incidents_by_status} />
      </div>

      {/* SECTION 4: Hotspots & Teams (Service Leaderboard + Team Queues) */}
      <div className="analytics-dual-grid">
        <ServiceHotspots items={analytics.incidents_by_application} onAsk={onAsk} />
        <TeamWorkload items={analytics.incidents_by_team} onAsk={onAsk} />
      </div>

      {/* SECTION 5: Root Causes Playbooks */}
      <RecurringRootCauses items={analytics.recurring_root_causes} onAsk={onAsk} />

      {/* SECTION 6: Knowledge Graph Topology */}
      {graphTopology && <KnowledgeGraph topology={graphTopology} />}
    </div>
  );
}
