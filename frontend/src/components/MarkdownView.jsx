import React from "react";

function formatInline(text) {
  // Replace bold **text** or __text__
  const parts = [];
  let remaining = text;
  let key = 0;

  const regex = /(\*\*(.*?)\*\*|`(.*?)`)/g;
  let match;
  let lastIndex = 0;

  while ((match = regex.exec(remaining)) !== null) {
    if (match.index > lastIndex) {
      parts.push(remaining.substring(lastIndex, match.index));
    }
    if (match[2]) {
      // Bold
      parts.push(<strong key={key++}>{match[2]}</strong>);
    } else if (match[3]) {
      // Code
      parts.push(<code key={key++} className="inline-code">{match[3]}</code>);
    }
    lastIndex = regex.lastIndex;
  }
  if (lastIndex < remaining.length) {
    parts.push(remaining.substring(lastIndex));
  }
  return parts.length ? parts : text;
}

export default function MarkdownView({ content }) {
  if (!content) return null;

  const lines = String(content).split("\n");
  const blocks = [];
  let currentList = null;

  lines.forEach((line, idx) => {
    const trimmed = line.trim();

    // Empty lines break lists
    if (!trimmed) {
      if (currentList) {
        blocks.push(currentList);
        currentList = null;
      }
      return;
    }

    // Header ## or ###
    if (trimmed.startsWith("### ")) {
      if (currentList) { blocks.push(currentList); currentList = null; }
      blocks.push(<h4 key={`h4-${idx}`} className="md-h4">{formatInline(trimmed.slice(4))}</h4>);
      return;
    }
    if (trimmed.startsWith("## ")) {
      if (currentList) { blocks.push(currentList); currentList = null; }
      blocks.push(<h3 key={`h3-${idx}`} className="md-h3">{formatInline(trimmed.slice(3))}</h3>);
      return;
    }
    if (trimmed.startsWith("# ")) {
      if (currentList) { blocks.push(currentList); currentList = null; }
      blocks.push(<h2 key={`h2-${idx}`} className="md-h2">{formatInline(trimmed.slice(2))}</h2>);
      return;
    }

    // Bullet points (- or * )
    if (/^[-*]\s+/.test(trimmed)) {
      const itemText = trimmed.replace(/^[-*]\s+/, "");
      if (!currentList || currentList.type !== "ul") {
        if (currentList) blocks.push(currentList);
        currentList = { type: "ul", items: [], key: `ul-${idx}` };
      }
      currentList.items.push(<li key={`li-${idx}`}>{formatInline(itemText)}</li>);
      return;
    }

    // Numbered list (1. )
    if (/^\d+\.\s+/.test(trimmed)) {
      const itemText = trimmed.replace(/^\d+\.\s+/, "");
      if (!currentList || currentList.type !== "ol") {
        if (currentList) blocks.push(currentList);
        currentList = { type: "ol", items: [], key: `ol-${idx}` };
      }
      currentList.items.push(<li key={`oli-${idx}`}>{formatInline(itemText)}</li>);
      return;
    }

    // Blockquote (> )
    if (trimmed.startsWith("> ")) {
      if (currentList) { blocks.push(currentList); currentList = null; }
      blocks.push(<blockquote key={`quote-${idx}`} className="md-quote">{formatInline(trimmed.slice(2))}</blockquote>);
      return;
    }

    // Normal paragraph line
    if (currentList) {
      blocks.push(currentList);
      currentList = null;
    }
    blocks.push(<p key={`p-${idx}`} className="md-p">{formatInline(trimmed)}</p>);
  });

  if (currentList) {
    blocks.push(currentList);
  }

  return (
    <div className="markdown-view">
      {blocks.map((block, i) => {
        if (block.type === "ul") {
          return <ul key={block.key || i} className="md-ul">{block.items}</ul>;
        }
        if (block.type === "ol") {
          return <ol key={block.key || i} className="md-ol">{block.items}</ol>;
        }
        return block;
      })}
    </div>
  );
}

