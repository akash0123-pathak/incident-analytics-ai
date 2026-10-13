import { useState } from "react";
import { IconArrowUpRight, IconSparkles, IconChevronDown } from "./Icons.jsx";
import { getRoleSuggestions } from "../roleSuggestions.js";


export default function NewInvestigation({ activeRole, onStart }) {
  const [brief, setBrief] = useState("");
  const [directiveOpen, setDirectiveOpen] = useState(false);
  const suggestions = getRoleSuggestions(activeRole?.id);
  const start = (question) => {
    const value = (question || brief).trim();
    if (value) onStart(value);
  };
  return <div className="investigation-workspace">
    <section className="investigation-hero">
      <span className="eyebrow">NEW CASE WORKSPACE</span>
      <h2>Start a focused investigation.</h2>
      <p>Choose an analysis directive, a template, or ask your own question to begin.</p>
    </section>
    <section className="command-actions investigation-templates">
      <div className="section-heading"><div><span className="eyebrow">QUICK INVESTIGATION TEMPLATES</span><h3>Suggested inquiries</h3></div><span>Role-tailored queries</span></div>
      <div className="action-grid">
        {suggestions.templates.map(([title, prompt]) => <button key={title} className="action-card" onClick={() => start(prompt)}><i><IconArrowUpRight size={16} /></i><b>{title}</b><span>{prompt}</span></button>)}
      </div>
    </section>
    <section className="investigation-composer">
      <div className="quick-tags-bar">
        <span className="quick-tags-label">Quick intent:</span>
        {suggestions.quickTags.map(([label, prompt]) => <button key={label} className="quick-tag-chip" onClick={() => start(prompt)}>{label}</button>)}
      </div>
      <div className="investigation-composer__row">
        <input value={brief} onChange={(event) => setBrief(event.target.value)} onKeyDown={(event) => event.key === "Enter" && start()} placeholder="Ask about incidents, trends, ownership, or resolution…" />
        <div className="investigation-send-menu">
          <button className="btn btn--primary" onClick={() => start()} disabled={!brief.trim()}><IconSparkles size={16} /> Send</button>
          <button className="btn btn--primary investigation-send-menu__toggle" onClick={() => setDirectiveOpen((open) => !open)} aria-label="Choose analysis directive"><IconChevronDown size={16} /></button>
          {directiveOpen && <div className="mode-dropdown-menu investigation-mode-dropdown"><div className="dropdown-menu-header">Select Analysis Directive</div>{suggestions.directives.map(([label, prompt, Icon, detail]) => <button key={label} className="dropdown-menu-item" onClick={() => { setDirectiveOpen(false); start(prompt); }}><Icon size={16} /><div><b>{label}</b><small>{detail}</small></div></button>)}</div>}
        </div>
      </div>
      <small>Press Enter to ask · Role: {activeRole?.label || "IT Support Engineer"}</small>
    </section>
  </div>;
}
