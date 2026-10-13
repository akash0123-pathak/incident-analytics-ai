import { useState } from "react";

const PROVIDERS = [
  { id: "nvidia", label: "NVIDIA NIM" },
  { id: "openai", label: "OpenAI" },
  { id: "anthropic", label: "Anthropic" },
];

export default function SettingsPanel({ config, keySource, setKeySource, apiKey, setApiKey, provider, setProvider }) {
  const [draftKey, setDraftKey] = useState(apiKey || "");
  const [saved, setSaved] = useState(false);

  const applyKey = () => {
    setApiKey(draftKey.trim());
    setKeySource("browser");
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  };

  const clearKey = () => {
    setDraftKey("");
    setApiKey("");
    setKeySource(config?.server_key_configured ? "background" : "none");
  };

  return (
    <div className="panel-block">
      <div className="panel-block__label">AI mode</div>

      <div className="settings-status" hidden>
        {keySource === "browser" && apiKey ? (
          <span className="pill pill--ai">AI-powered · key from this browser</span>
        ) : keySource === "background" ? (
          <span className="pill pill--ai">AI-powered · server key (background)</span>
        ) : (
          <span className="pill pill--dataset">MCP · DuckDB · no key in use</span>
        )}
      </div>

      <label className="field-label" htmlFor="provider-select">
        Provider
      </label>
      <select
        id="provider-select"
        className="select"
        value={provider}
        onChange={(e) => setProvider(e.target.value)}
      >
        {PROVIDERS.map((p) => (
          <option key={p.id} value={p.id}>
            {p.label}
          </option>
        ))}
      </select>

      <label className="field-label" htmlFor="api-key-input">
        API key (this browser only)
      </label>
      <input
        id="api-key-input"
        className="text-input"
        type="password"
        placeholder="nvapi-... / sk-... / sk-ant-..."
        value={draftKey}
        onChange={(e) => setDraftKey(e.target.value)}
        autoComplete="off"
      />
      <p className="field-hint">
        Stored only in this browser's local storage and sent with your requests.
        It is never written to disk on the server.
      </p>

      <div className="settings-actions">
        <button className="btn btn--primary" onClick={applyKey} disabled={!draftKey.trim()}>
          {saved ? "Saved" : "Use this key"}
        </button>
        <button className="btn btn--ghost" onClick={clearKey}>
          Clear
        </button>
      </div>

      <div className="settings-divider" />

      <div className="field-hint">
        {config?.server_key_configured ? (
          <>
            A background key is configured on the server
            {config.server_provider ? ` (${config.server_provider})` : ""}. Clearing
            your browser key falls back to it automatically.
          </>
        ) : (
          <>
            No server-side key is configured. To enable AI mode for every user
            without asking them to paste a key, set <code>NVIDIA_API_KEY</code> (or{" "}
            <code>OPENAI_API_KEY</code> / <code>ANTHROPIC_API_KEY</code>) in{" "}
            <code>backend/.env</code> — see the README.
          </>
        )}
      </div>
    </div>
  );
}
