import { useEffect, useRef, useState } from "react";
import ResultsTable from "./ResultsTable.jsx";
import ReportDownload from "./ReportDownload.jsx";
import KnowledgeGraph from "./KnowledgeGraph.jsx";
import MarkdownView from "./MarkdownView.jsx";
import {
  IconCopy,
  IconCheck,
  IconSparkles,
  IconArrowUpRight,
  IconClock,
  IconAlertTriangle,
  IconChevronDown,
  IconFileText,
  IconSend,
  IconX,
  IconCornerDownLeft,
  IconWand,
  IconSearch,
  IconTrendingUp,
} from "./Icons.jsx";
import { getRoleSuggestions } from "../roleSuggestions.js";

const ROLE_STARTERS = {
  engineer: {
    intro: "Investigate active incidents, technical causes, ownership, and service impact.",
    questions: [
      "Which critical incidents are not resolved?",
      "Show details for the AWS outage reported last month.",
      "Which incidents affect PaymentGateway and who owns them?",
      "What is the blast radius of the most common root cause?",
      "Show recurring incidents with their linked applications and teams.",
    ],
  },
  manager: {
    intro: "Monitor workload, service trends, recurring causes, and delivery risk.",
    questions: [
      "Which teams have the highest unresolved incident workload this quarter?",
      "Which applications generated the most critical incidents this quarter?",
      "What recurring root causes should the team prioritize?",
      "Show the trend of open and critical incidents over the last 90 days.",
      "Generate an operational incident report for this quarter.",
    ],
  },
  executive: {
    intro: "Review business risk, major incidents, recovery health, and strategic trends.",
    questions: [
      "How many critical incidents were reported this quarter?",
      "Which applications represent the highest incident risk this quarter?",
      "What are the top three recurring risks and recommended controls?",
      "How is incident volume trending compared with the previous period?",
      "Generate an executive incident risk report for the last 90 days.",
    ],
  },
};

const QUERY_MODES = [
  { id: "auto", label: "Smart Triage", icon: IconSparkles, prefix: "" },
  { id: "report", label: "Generate Report", icon: IconFileText, prefix: "Generate a comprehensive report on: " },
  { id: "trend", label: "Trend Analysis", icon: IconTrendingUp, prefix: "Analyze incident velocity and trend for: " },
  { id: "root_cause", label: "Root Cause Map", icon: IconAlertTriangle, prefix: "Map recurring root causes and blast radius for: " },
  { id: "lookup", label: "Incident Lookup", icon: IconSearch, prefix: "List specific matching incidents for: " },
];

const QUICK_TAGS = [
  { label: "📄 Generate Report", prompt: "Generate an executive incident report for this quarter with KPI statistics." },
  { label: "📈 90-Day Trend", prompt: "Show the trend of open and critical incidents over the last 90 days." },
  { label: "🕸️ Root Cause Map", prompt: "What is the blast radius and affected applications of recurring root causes?" },
  { label: "🚨 Critical Unresolved", prompt: "Which critical incidents are currently open or unresolved?" },
  { label: "👥 Team Workload", prompt: "Which team has the highest open incident workload right now?" },
];

function getIntentBadge(intent) {
  const classified = intent?.classified_intent || intent?.nlp_intent;
  switch (classified) {
    case "report":
      return { label: "📄 Generate Report", color: "badge--blue" };
    case "analysis":
      return { label: "📈 Trend Analysis", color: "badge--amber" };
    case "relationship_analysis":
      return { label: "🕸️ Knowledge Graph", color: "badge--purple" };
    case "lookup":
      return { label: "⚡ Direct Query", color: "badge--emerald" };
    default:
      return null;
  }
}

function AssistantMessage({ m, showEvidenceTable }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(m.text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const intentBadge = getIntentBadge(m.intent);
  const evidenceTable = showEvidenceTable && <ResultsTable rows={m.data} />;

  return (
    <div className="msg__bubble msg__bubble--assistant">
      <div className="msg__meta">
        <div className="meta-left">
          <span className={`pill ${m.modeUsed === "langgraph_ai" ? "pill--ai" : "pill--dataset"}`}>
            <IconSparkles size={12} />
            {m.modeUsed === "langgraph_ai"
              ? "AI Assistant"
              : "Deterministic · DuckDB"}
          </span>

          {intentBadge && (
            <span className={`pill ${intentBadge.color}`}>
              {intentBadge.label}
            </span>
          )}

          <span className="msg__matched">{m.matchedCount} records matched</span>
        </div>

        <button className="btn-icon" onClick={handleCopy} title="Copy response to clipboard">
          {copied ? <IconCheck size={14} className="text-emerald" /> : <IconCopy size={14} />}
          <span>{copied ? "Copied" : "Copy"}</span>
        </button>
      </div>

      {m.filterResult && evidenceTable}

      <div className="msg__content">
        <MarkdownView content={m.text} />
      </div>

      {m.relationshipGraph?.nodes?.length > 0 && <KnowledgeGraph topology={m.relationshipGraph} />}
      <ReportDownload report={m.report} relationshipGraph={m.relationshipGraph} />
      {!m.filterResult && evidenceTable}
    </div>
  );
}

export default function ChatWindow({ messages, onAsk, loading, activeRole, analytics, isInvestigation = false }) {
  const [input, setInput] = useState("");
  const [activeMode, setActiveMode] = useState("auto");
  const [menuOpen, setMenuOpen] = useState(false);
  const scrollRef = useRef(null);
  const latestResultRef = useRef(null);
  const menuRef = useRef(null);
  const quickTags = getRoleSuggestions(activeRole?.id).quickTags;

  useEffect(() => {
    // Command Center positions the newest table at the top of the results
    // pane, leaving the complete filter panel visible above it.
    if (isInvestigation) scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
    else latestResultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [messages, loading, isInvestigation]);

  // Close dropdown menu on click outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    setMenuOpen(isInvestigation && activeRole?.id === "executive");
  }, [activeRole?.id, isInvestigation]);

  const submit = (overrideText, modeId = activeMode) => {
    let q = (overrideText ?? input).trim();
    if (!q || loading) return;

    // Apply mode prefix if not already present
    const selectedMode = QUERY_MODES.find((m) => m.id === modeId);
    if (selectedMode?.prefix && !q.toLowerCase().includes("report") && !q.toLowerCase().includes("trend")) {
      q = `${selectedMode.prefix}${q}`;
    }

    onAsk(q);
    setInput("");
    setMenuOpen(false);
  };

  const handleActionSelect = (mode) => {
    setActiveMode(mode.id);
    setMenuOpen(false);
    if (input.trim()) {
      submit(input, mode.id);
    }
  };

  const showEvidenceTable = (message) => {
    return message.report || message.data?.length > 0;
  };

  return (
    <div className="chat">
      <div className="chat__scroll" ref={scrollRef}>
        {false && (
          <div className="command-home">
            <section className="command-hero">
              <div>
                <span className="eyebrow">OPERATIONAL QUEUE</span>
                <h2>Command center</h2>
                <p>Use a queue filter to open a governed incident table, then ask follow-up questions about that selected operational scope.</p>
              </div>
              <div className="command-hero__badge">
                <b>{activeRole?.label || "IT Support Engineer"}</b>
                <small>Active Workspace</small>
              </div>
            </section>

            <div className="command-metrics">
              <div className="command-metric-tile">
                <span className="metric-tile__label">Open Queue</span>
                <b className="metric-tile__val">{analytics?.open_incidents ?? "—"}</b>
                <small className="metric-tile__sub">Active incidents</small>
              </div>
              <div className="command-metric-tile">
                <span className="metric-tile__label">Critical Risk</span>
                <b className="metric-tile__val text-crimson">{analytics?.critical_incidents ?? "—"}</b>
                <small className="metric-tile__sub">P1 Priority</small>
              </div>
              <div className="command-metric-tile">
                <span className="metric-tile__label">Resolution MTTR</span>
                <b className="metric-tile__val">{analytics ? `${analytics.average_resolution_hours}h` : "—"}</b>
                <small className="metric-tile__sub">Average recovery</small>
              </div>
              <div className="command-metric-tile">
                <span className="metric-tile__label">Resolved</span>
                <b className="metric-tile__val text-emerald">{analytics?.resolved_incidents ?? "—"}</b>
                <small className="metric-tile__sub">Closed or verified</small>
              </div>
            </div>

            <section className="command-actions command-filters">
              <div className="section-heading">
                <div>
                  <span className="eyebrow">QUEUE FILTERS</span>
                  <h3>Choose an operational view</h3>
                </div>
                <span>Each button returns a filtered table</span>
              </div>
              <div className="action-grid">
                {queueFilters.map(([label, query]) => (
                  <button key={label} className="action-card" onClick={() => submit(query, "lookup")}>
                    <i><IconArrowUpRight size={16} /></i>
                    <b>{label}</b>
                    <span>Open matching incident table</span>
                  </button>
                ))}
              </div>
            </section>
          </div>
        )}

        {messages.filter((m) => !m.hidden).map((m, i, visibleMessages) => (
          <div key={i} ref={!isInvestigation && i === visibleMessages.length - 1 ? latestResultRef : null} className={`msg msg--${m.role}`}>
            {m.role === "user" ? (
              <div className="msg__bubble msg__bubble--user">{m.text}</div>
            ) : (
              <AssistantMessage m={m} showEvidenceTable={showEvidenceTable(m)} />
            )}
          </div>
        ))}

        {loading && (
          <div className="msg msg--assistant">
            <div className="msg__bubble msg__bubble--assistant msg__bubble--loading">
              <div className="pulse-dots">
                <span />
                <span />
                <span />
              </div>
              <span>Querying incident warehouse and synthesizing operational insights…</span>
            </div>
          </div>
        )}
      </div>

      {/* RICH MULTI-ACTION INPUT COMMAND BAR */}
      <div className="chat__input-row">
        {isInvestigation && <div className="quick-tags-bar">
          <span className="quick-tags-label">Quick Intent:</span>
          {quickTags.map(([label, prompt]) => (
            <button
              key={label}
              className="quick-tag-chip"
              onClick={() => submit(prompt)}
              disabled={loading}
              title={`Ask: "${prompt}"`}
            >
              {label}
            </button>
          ))}
        </div>}

        <div className="chat__command-bar">
          {/* Main Input Textarea/Field */}
          <div className="chat__input-wrapper">
            <input
              className="text-input chat__input"
              placeholder={
                activeMode === "report"
                  ? "Enter scope for executive report (e.g. Critical incidents last 90 days)…"
                  : activeMode === "trend"
                  ? "Enter services or categories to analyze trend over time…"
                  : activeMode === "root_cause"
                  ? "Enter outage or service to map root causes & blast radius…"
                  : "Ask about incidents, weekly trends, root causes, or blast radius…"
              }
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  submit();
                }
              }}
            />

            {input.trim() && (
              <button
                type="button"
                className="input-clear-btn"
                onClick={() => setInput("")}
                title="Clear input"
              >
                <IconX size={14} />
              </button>
            )}
          </div>

          {/* Multi-Action Split Send Button */}
          <div className="split-action-group" ref={menuRef}>
            <button
              className="btn btn--primary split-btn-main"
              onClick={() => submit()}
              disabled={loading || !input.trim()}
              title="Submit query (Enter)"
              aria-label="Send query"
            >
              {loading ? (
                <>
                  <div className="btn-spinner" />
                </>
              ) : (
                <IconSend size={18} />
              )}
            </button>

            {isInvestigation && activeRole?.id === "executive" && <button
              className="btn btn--primary split-btn-dropdown"
              onClick={() => setMenuOpen(!menuOpen)}
              disabled={loading}
              title="More actions"
            >
              <IconChevronDown size={14} />
            </button>}

            {isInvestigation && activeRole?.id === "executive" && menuOpen && (
              <div className="mode-dropdown-menu">
                <div className="dropdown-menu-header">Select Analysis Directive</div>
                {QUERY_MODES.map((mode) => {
                  const ModeIcon = mode.icon;
                  return (
                    <button
                      key={mode.id}
                      type="button"
                      className={`dropdown-menu-item ${activeMode === mode.id ? "dropdown-menu-item--active" : ""}`}
                      onClick={() => handleActionSelect(mode)}
                    >
                      <ModeIcon size={16} />
                      <div>
                        <b>{mode.label}</b>
                        <small>
                          {mode.id === "auto" && "Intent auto-classification"}
                          {mode.id === "report" && "Full KPIs, charts & Word doc"}
                          {mode.id === "trend" && "Frequency, surges & velocity"}
                          {mode.id === "root_cause" && "Blast radius & service impact"}
                          {mode.id === "lookup" && "Raw matching incident rows"}
                        </small>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Input Bar Helper Footer */}
        <div className="input-helper-row">
          <span>Press <b>Enter ↵</b> to ask &middot; <b>Shift + Enter</b> for new line</span>
          <span>Role: <b>{activeRole?.label}</b></span>
        </div>
      </div>
    </div>
  );
}
