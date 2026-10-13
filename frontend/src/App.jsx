import { useEffect, useState } from "react";
import RoleSelector from "./components/RoleSelector.jsx";
import ChatHistory from "./components/ChatHistory.jsx";
import ChatWindow from "./components/ChatWindow.jsx";
import AnalyticsDashboard from "./components/AnalyticsDashboard.jsx";
import DatasetPanel from "./components/DatasetPanel.jsx";
import LoginGate from "./components/LoginGate.jsx";
import LiveIncidents from "./components/LiveIncidents.jsx";
import { analyzeLiveIncidents, fetchRoles, fetchConfig, fetchAnalytics, fetchKnowledgeGraphTopology, fetchLiveIncidentStatus, fetchLiveIncidents, login, postQuery, register, reloadDataset, roleLogin, setSessionToken } from "./api.js";
import KnowledgeGraph from "./components/KnowledgeGraph.jsx";
import RolePinModal from "./components/RolePinModal.jsx";
import NewInvestigation from "./components/NewInvestigation.jsx";
import CommandFilters from "./components/CommandFilters.jsx";

function makeSession(roleId, messages = []) {
  return {
    id: `${roleId}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    title: "",
    messages,
  };
}

function sessionTitle(roleId, question) {
  const slug = question
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 34) || "incident_analysis";
  return `${roleId}_query_${slug}`;
}

function loadChatHistory() {
  try {
    const saved = window.localStorage.getItem("incident-analytics-chat-history");
    if (saved) return JSON.parse(saved);
  } catch {
    // A blocked or malformed browser store should not prevent the chat UI.
  }
  return { sessions: {}, activeSessionIds: {} };
}

export default function App() {
  const [roles, setRoles] = useState([]);
  const [role, setRole] = useState("engineer");
  const [config, setConfig] = useState(null);
  const [chatHistory, setChatHistory] = useState(loadChatHistory);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [graphTopology, setGraphTopology] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [view, setView] = useState("chat");
  const [workspace, setWorkspace] = useState("command");
  const [commandFilters, setCommandFilters] = useState({});
  const [liveStatus, setLiveStatus] = useState(null);
  const [liveFeed, setLiveFeed] = useState(null);
  const [liveLoading, setLiveLoading] = useState(false);
  const [liveAnalyzing, setLiveAnalyzing] = useState(false);
  const [liveAnalysis, setLiveAnalysis] = useState(null);
  const [liveError, setLiveError] = useState(null);
  const [session, setSession] = useState(() => {
    try { return JSON.parse(window.localStorage.getItem("incident-analytics-session")); } catch { return null; }
  });
  const [requestedRole, setRequestedRole] = useState("engineer");
  const [loginError, setLoginError] = useState(null);
  const [loggingIn, setLoggingIn] = useState(false);
  const [rolePinRequest, setRolePinRequest] = useState(null);
  const activeRole = roles.find((item) => item.id === role);
  const workspaceKey = `${workspace}:${role}`;
  const sessions = chatHistory.sessions[workspaceKey] || [];
  // `null` is meaningful here: it represents the blank workspace created by
  // New chat / Clear chat. Do not fall back to the first saved conversation.
  const activeSessionId = Object.hasOwn(chatHistory.activeSessionIds, workspaceKey)
    ? chatHistory.activeSessionIds[workspaceKey]
    : sessions[0]?.id || null;
  const activeSession = sessions.find((session) => session.id === activeSessionId);
  const messages = activeSession?.messages || [];
  const historySessionsByRole = Object.fromEntries(
    ["engineer", "manager", "executive"].map((roleId) => [
      roleId,
      ["command", "investigation"].flatMap((space) => (chatHistory.sessions[`${space}:${roleId}`] || []).map((item) => ({ ...item, workspace: space })))
        .filter((session) => session.messages.length > 0)
        .sort((a, b) => b.id.localeCompare(a.id)),
    ]),
  );

  useEffect(() => {
    fetchRoles().then(setRoles).catch(() => setError("Could not reach the backend API."));
    fetchConfig()
      .then((cfg) => {
        setConfig(cfg);
      })
      .catch(() => setError("Could not reach the backend API."));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!session?.token) return;
    setSessionToken(session.token);
    setRole(session.role);
    Promise.all([fetchAnalytics(), fetchKnowledgeGraphTopology()])
      .then(([summary, topology]) => { setAnalytics(summary); setGraphTopology(topology); })
      .catch(() => {
        setSessionToken(null);
        window.localStorage.removeItem("incident-analytics-session");
        setSession(null);
      });
    fetchLiveIncidentStatus().then(setLiveStatus).catch(() => setLiveStatus({ configured: false, message: "Could not check the live incident connection." }));
  }, [session]);

  useEffect(() => {
    try {
      window.localStorage.setItem("incident-analytics-chat-history", JSON.stringify(chatHistory));
    } catch {
      // Keep the active conversation usable if browser storage is unavailable.
    }
  }, [chatHistory]);

  const selectRole = (nextRole) => {
    if (nextRole !== session?.role) {
      if (nextRole !== "engineer") {
        setLoginError(null);
        setRolePinRequest(nextRole);
        return;
      }
      setRequestedRole(nextRole);
      signIn(nextRole, "");
      return;
    }
    setChatHistory((current) => {
      const targetKey = `${workspace}:${nextRole}`;
      const roleSessions = current.sessions[targetKey] || [];
      const initialSession = roleSessions[0] || makeSession(nextRole);
      return {
        sessions: { ...current.sessions, [targetKey]: roleSessions.length ? roleSessions : [initialSession] },
        activeSessionIds: { ...current.activeSessionIds, [targetKey]: current.activeSessionIds[targetKey] || initialSession.id },
      };
    });
    setRole(nextRole);
    setView("chat");
  };

  const signIn = async (nextRole, pin) => {
    setLoggingIn(true); setLoginError(null);
    try {
      const nextSession = await roleLogin({ role: nextRole, pin });
      setSessionToken(nextSession.token);
      setSession(nextSession);
      window.localStorage.setItem("incident-analytics-session", JSON.stringify(nextSession));
      setRolePinRequest(null);
      setLoginError(null);
    } catch (err) { setLoginError(err?.response?.data?.detail || "Unable to verify this role PIN."); }
    finally { setLoggingIn(false); }
  };

  const authenticateAccount = async ({ mode, email, password }) => {
    setLoggingIn(true); setLoginError(null);
    try {
      const nextSession = mode === "register" ? await register({ email, password }) : await login({ email, password });
      setSessionToken(nextSession.token);
      setSession(nextSession);
      window.localStorage.setItem("incident-analytics-session", JSON.stringify(nextSession));
    } catch (err) { setLoginError(err?.response?.data?.detail || "Unable to authenticate this account."); }
    finally { setLoggingIn(false); }
  };

  if (!session?.token) {
    return <LoginGate onAuthenticate={authenticateAccount} loading={loggingIn} error={loginError} />;
  }

  const requestedRoleDetails = roles.find((item) => item.id === rolePinRequest);

  const newChat = (targetWorkspace = workspace) => {
    const targetKey = `${targetWorkspace}:${role}`;
    setChatHistory((current) => ({
      ...current,
      activeSessionIds: { ...current.activeSessionIds, [targetKey]: null },
    }));
    setWorkspace(targetWorkspace);
    setView(targetWorkspace === "investigation" ? "new" : "chat");
  };

  const selectSession = (sessionRole, sessionId, sessionWorkspace = "command") => {
    const targetKey = `${sessionWorkspace}:${sessionRole}`;
    setChatHistory((current) => ({ ...current, activeSessionIds: { ...current.activeSessionIds, [targetKey]: sessionId } }));
    setRole(sessionRole);
    setWorkspace(sessionWorkspace);
    setView("chat");
  };

  const appendToRoleSession = (roleId, message, targetWorkspace = workspace) => {
    const targetKey = `${targetWorkspace}:${roleId}`;
    setChatHistory((current) => {
      const roleSessions = current.sessions[targetKey] || [];
      const currentId = current.activeSessionIds[targetKey];
      // A null active id means the user deliberately clicked New chat, so do
      // not append the next question to an older conversation.
      const base = (currentId && roleSessions.find((session) => session.id === currentId)) || makeSession(roleId);
      const updated = {
        ...base,
        title: base.messages.length === 0 && message.role === "user" ? sessionTitle(roleId, message.text) : base.title,
        messages: [...base.messages, message],
      };
      const replaced = roleSessions.some((session) => session.id === base.id)
        ? roleSessions.map((session) => session.id === base.id ? updated : session)
        : [updated, ...roleSessions];
      return { sessions: { ...current.sessions, [targetKey]: replaced }, activeSessionIds: { ...current.activeSessionIds, [targetKey]: base.id } };
    });
  };

  const clearActiveSession = () => {
    // Keep the completed conversation in history; clear only the visible
    // workspace by starting an unsaved blank chat for the current role.
    newChat();
  };

  const refreshDataset = async () => {
    setRefreshing(true);
    setError(null);
    try {
      await reloadDataset();
      const [cfg, summary, topology] = await Promise.all([fetchConfig(), fetchAnalytics(), fetchKnowledgeGraphTopology()]);
      setConfig(cfg);
      setAnalytics(summary);
      setGraphTopology(topology);
    } catch {
      setError("Dataset refresh failed. Check that the backend is running.");
    } finally {
      setRefreshing(false);
    }
  };

  const fetchLiveFeed = async () => {
    if (session.role !== "engineer") return;
    setLiveLoading(true); setLiveError(null);
    try { setLiveAnalysis(null); setLiveFeed(await fetchLiveIncidents()); }
    catch (err) { setLiveError(err?.response?.data?.detail || "Could not fetch live incidents."); }
    finally { setLiveLoading(false); }
  };

  const analyzeLiveFeed = async () => {
    if (session.role !== "engineer") return;
    setLiveAnalyzing(true); setLiveError(null);
    try {
      const result = await analyzeLiveIncidents("Summarize the current live incidents, identify the highest-priority operational risk, likely owners, and the next action to take.");
      setLiveFeed(result);
      setLiveAnalysis(result.answer || null);
    } catch (err) { setLiveError(err?.response?.data?.detail || "Could not analyze live incidents."); }
    finally { setLiveAnalyzing(false); }
  };

  const ask = async (question, targetWorkspace = workspace, scopeOverride, hideUserMessage = false) => {
    const roleAtQuestion = role;
    setWorkspace(targetWorkspace);
    setView("chat");
    const previousQuestion = [...messages].reverse().find((message) => message.role === "user")?.text;
    const isExplicitFollowUp = /\b(these|those|them|above|previous|same|ones|it|they|their|related|relationship)\b/i.test(question)
      // A short status-only prompt after a scoped query is also a follow-up:
      // e.g. "what are resolved?" after "AWS unresolved issues".
      || (messages.length > 0 && /^\s*(?:w(?:hat|ht)|which|show|list)?\s*(?:are|is)?\s*(?:open|closed|resolved|unresolved|active|critical|high|medium|low)(?:\s+(?:issues?|incidents?|ones?))?\s*\??\s*$/i.test(question));
    appendToRoleSession(roleAtQuestion, { role: "user", text: question, hidden: hideUserMessage }, targetWorkspace);
    setLoading(true);
    setError(null);
    const appendAnswer = (res) => appendToRoleSession(roleAtQuestion,
      {
        role: "assistant",
        text: res.answer,
        data: res.data,
        matchedCount: res.matched_count,
        modeUsed: res.mode_used,
        provider: res.provider,
        intent: res.intent,
        report: res.report,
        relationshipGraph: res.relationship_graph,
        filterResult: hideUserMessage,
      }, targetWorkspace);
    const activeScope = targetWorkspace === "command" ? scopeOverride ?? Object.values(commandFilters).filter(Boolean).map((item) => item.query).join(" ") : "";
    const scopedQuestion = activeScope && question !== activeScope ? `${question}\nFILTER SCOPE: ${activeScope}` : question;
    try {
      const res = await postQuery({ question: scopedQuestion, role, contextQuestion: isExplicitFollowUp ? previousQuestion : null });
      appendAnswer(res);
    } catch (e) {
      // IT Support can recover transparently from an expired in-memory API
      // session, then retry the question once with the replacement token.
      if (e?.response?.status === 401 && roleAtQuestion === "engineer") {
        try {
          setSession(null);
          setSessionToken(null);
          return;
        } catch (retryError) {
          e = retryError;
        }
      }
      appendToRoleSession(roleAtQuestion,
        {
          role: "assistant",
          text: `Something went wrong: ${e?.response?.data?.detail || e.message}`,
          data: [],
          matchedCount: 0,
          modeUsed: "dataset",
        }, targetWorkspace);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="sidebar__brand">
          <div className="sidebar__brand-mark">◈</div>
          <div>
            <div className="sidebar__brand-title">SignalDeck</div>
            <div className="sidebar__brand-sub">Incident operations workspace</div>
          </div>
        </div>

        <nav className="workspace-nav" aria-label="Workspace navigation">
          <button className={`workspace-nav__item ${view === "chat" && workspace === "command" ? "workspace-nav__item--active" : ""}`} onClick={() => { setWorkspace("command"); setView("chat"); }}><span>⌁</span> Command center</button>
          <button className={`workspace-nav__item ${view === "analytics" ? "workspace-nav__item--active" : ""}`} onClick={() => setView("analytics")}><span>▥</span> Analytics board</button>
          <button className={`workspace-nav__item ${view === "new" || workspace === "investigation" ? "workspace-nav__item--active" : ""}`} onClick={() => newChat("investigation")}><span>＋</span> New investigation</button>
          <button className={`workspace-nav__item ${view === "live" ? "workspace-nav__item--active" : ""}`} onClick={() => setView("live")}><span>◉</span> Live incidents</button>
        </nav>

        {roles.length > 0 && <RoleSelector roles={roles} selectedRole={role} onChange={selectRole} />}

        <DatasetPanel config={config} onRefresh={refreshDataset} refreshing={refreshing} onClearChat={clearActiveSession} canRefresh={session.role === "engineer"} />
        <ChatHistory sessionsByRole={historySessionsByRole} activeRole={role} activeSessionId={activeSessionId} onNewChat={newChat} onSelect={selectSession} />

        {error && <div className="sidebar__error">{error}</div>}
      </aside>

      <main className="main">
        <header className="main__header">
          <div>
            <div className="eyebrow">Operations intelligence / {view === "chat" || view === "new" ? workspace === "investigation" ? "Investigation" : "Command queue" : view === "live" ? "Live intake" : "Portfolio health"}</div>
            <h1>{view === "chat" ? workspace === "investigation" ? "Investigation workspace" : "Incident command center" : view === "new" ? "New investigation" : view === "live" ? "Live incident feed" : "Operational analytics"}</h1>
            <p>{view === "chat" ? workspace === "investigation" ? `Focused investigation conversation. Viewing as ${activeRole?.label || "IT Support Engineer"}.` : `Use a queue filter, then ask follow-up questions on the selected incident set. Viewing as ${activeRole?.label || "IT Support Engineer"}.` : view === "new" ? "Start a fresh investigation with a blank conversation workspace." : view === "live" ? "Read-only Jira Service Management incidents, kept separate from the historical warehouse." : "Live operational indicators from the current incident warehouse."}</p>
          </div>
          <div className="header-status">
            <span className="status-dot" />
            <div><b>{config ? "Warehouse connected" : "Connecting"}</b><small>{config ? `${config.total_incidents.toLocaleString()} governed records` : "Loading workspace"}</small></div>
            {session.role === "engineer" && <button className="btn btn--ghost" onClick={refreshDataset} disabled={refreshing}>{refreshing ? "Refreshing…" : "Refresh"}</button>}
          </div>
        </header>
        {view === "analytics" ? (
          <AnalyticsDashboard analytics={analytics} graphTopology={graphTopology} onAsk={(question) => { newChat("investigation"); ask(question, "investigation"); }} loading={loading} activeRole={activeRole} />
        ) : view === "live" ? (
          <LiveIncidents status={liveStatus} feed={liveFeed} analysis={liveAnalysis} loading={liveLoading} analyzing={liveAnalyzing} error={liveError} canFetch={session.role === "engineer"} onFetch={fetchLiveFeed} onAnalyze={analyzeLiveFeed} />
        ) : view === "new" ? (
          <NewInvestigation activeRole={activeRole} onStart={(question) => ask(question, "investigation")} />
        ) : (
          <>{workspace === "command" && <CommandFilters selected={commandFilters} onChange={(next) => { setCommandFilters(next); const scope = Object.values(next).filter(Boolean).map((item) => item.query).join(" "); ask(scope || "Show all incidents.", "command", scope, true); }} />}<ChatWindow messages={messages} onAsk={ask} loading={loading} activeRole={activeRole} analytics={analytics} isInvestigation={workspace === "investigation"} /></>
        )}
      </main>
      {rolePinRequest && (
        <RolePinModal
          role={rolePinRequest}
          roleLabel={requestedRoleDetails?.label || (rolePinRequest === "manager" ? "Engineering Manager" : "Executive")}
          onSubmit={(pin) => signIn(rolePinRequest, pin)}
          onClose={() => { setRolePinRequest(null); setLoginError(null); }}
          loading={loggingIn}
          error={loginError}
        />
      )}
    </div>
  );
}
