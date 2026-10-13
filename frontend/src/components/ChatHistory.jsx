const ROLE_LABELS = {
  engineer: "IT Support Engineer",
  manager: "Engineering Manager",
  executive: "Executive",
};

export default function ChatHistory({ sessionsByRole, activeRole, activeSessionId, onNewChat, onSelect }) {
  return (
    <div className="panel-block chat-history">
      <div className="chat-history__heading">
        <div className="panel-block__label">Chat history</div>
        <button className="btn btn--ghost chat-history__new" onClick={onNewChat}>New chat</button>
      </div>
      {Object.values(sessionsByRole).flat().length === 0 ? (
        <div className="field-hint">No saved conversations for this role.</div>
      ) : (
        <div className="chat-history__list">
          {Object.entries(ROLE_LABELS).map(([roleId, label]) => {
            const sessions = sessionsByRole[roleId] || [];
            if (!sessions.length) return null;
            return (
              <div className="chat-history__group" key={roleId}>
                <div className="chat-history__group-label">{label} · {sessions.length}</div>
                {sessions.map((session) => (
                  <button
                    key={session.id}
                    className={`chat-history__item ${roleId === activeRole && session.id === activeSessionId ? "chat-history__item--active" : ""}`}
                    onClick={() => onSelect(roleId, session.id, session.workspace)}
                    title={session.title}
                  >
                    <span>{session.title}</span>
                    <small>{session.workspace === "investigation" ? "Investigation" : "Command queue"} · {session.messages.length} message{session.messages.length === 1 ? "" : "s"}</small>
                  </button>
                ))}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
