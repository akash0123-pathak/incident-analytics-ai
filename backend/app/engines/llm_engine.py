"""
AI-powered engine - only used when an API key is available (from the
frontend Settings panel, per-request, or a server-side/background key).

Design: retrieval-then-generate, NOT fine-tuning or embeddings.
  1. Reuse the deterministic dataset_engine to filter the CSV down to the
     rows relevant to the question (role-aware, same logic as the free tier).
  2. Hand that filtered data + the question to the LLM via LangChain so it
     writes a fuller, more natural, "best" answer than the templated one.

This keeps ML usage to (effectively) zero: the retrieval step is the same
rule-based pandas filter used in dataset_engine.py. Only the final answer
composition step calls out to a model.
"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from ..roles import Role
from ..config import (PROVIDER_BASE_URLS, PROVIDER_DEFAULT_MODELS,
                      configured_provider_keys, provider_model_candidates)
from . import dataset_engine

# Avoid making every user wait through the same known provider outage. A
# provider that fails is skipped briefly; the preferred provider is retried
# automatically after the cooldown instead of being permanently disabled.
_PROVIDER_COOLDOWN_UNTIL: dict[str, float] = {}
_PROVIDER_COOLDOWN_SECONDS = 60


def _safe_provider_error(exc: Exception) -> str:
    """Return a short diagnostic without ever including credentials."""
    detail = str(exc).replace("\n", " ").strip()
    # SDK errors can echo a request URL or headers in some failure modes.
    detail = re.sub(r"(?i)(api[_ -]?key|authorization)\s*[:=]\s*\S+", r"\1=[redacted]", detail)
    return detail[:240] or type(exc).__name__

SYSTEM_PROMPT = """You are an Incident Management analytics assistant.
You answer questions about IT incidents using ONLY the incident data provided
in the context below. Use clear, natural operational language: lead with a
direct answer in one or two short sentences, then use bullets only when they
make several facts easier to scan. Do not sound like a database export.
Return plain text only: do not use Markdown symbols such as **, #, backticks,
or tables, because the product renders the answer as readable text.
If the context does not contain enough information to answer, say so plainly.
Tailor the level of detail to the audience: {audience_hint}
Never invent incident IDs, dates, or root causes that are not in the context.
The deterministic retrieval count is authoritative. The rows may be a display
sample, so never replace the authoritative count with the number of rows shown.
The web UI displays the matched incident rows in a table below your answer.
For ordinary lookup, filter, or status questions, write a concise natural-
language summary instead of repeating incident IDs, titles, or row fields.
Mention the total count and the most useful aggregate patterns, such as the
date range, severity/status distribution, leading applications, teams, or
root causes. Do not use an incident list unless the user explicitly asks to
list, enumerate, show IDs, or provide incident details.
"""

AUDIENCE_HINTS = {
    "raw": "This is an engineer - include incident IDs, root causes, and technical detail.",
    "summary": "This is an engineering manager - summarize trends and team workload, omit individual reporter names.",
    "executive": "This is an executive - keep it to headline numbers, critical incidents, and overall trend. No low-level detail.",
}


class _GeminiResponse:
    def __init__(self, content: str):
        self.content = content


class _GeminiChat:
    """Small Gemini REST adapter with the same ``invoke`` shape used below."""

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def invoke(self, messages) -> _GeminiResponse:
        if not isinstance(messages, list):
            messages = [messages]
        system_parts, user_parts = [], []
        for message in messages:
            text = str(getattr(message, "content", message))
            if getattr(message, "type", "") == "system":
                system_parts.append(text)
            else:
                user_parts.append(text)
        payload = {
            "contents": [{"role": "user", "parts": [{"text": "\n\n".join(user_parts)}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1200},
        }
        if system_parts:
            payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
        endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            + urllib.parse.quote(self.model, safe="") + ":generateContent"
        )
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = json.load(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"Gemini API returned HTTP {exc.code}: {detail}") from exc
        candidates = body.get("candidates", [])
        parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
        text = "".join(str(part.get("text", "")) for part in parts).strip()
        if not text:
            raise RuntimeError("Gemini returned no text response")
        return _GeminiResponse(text)

INTENT_NORMALIZER_PROMPT = """Normalize this incident-analytics request for a
deterministic database search. Return JSON only: {"query": "..."}.

The input can contain an earlier scope followed by `Follow-up:` and the newest
request. Preserve the earlier application, status, category, and time scope
when the newest request refers to "these", "those", "it", or "ones". A newer
status replaces an older status. Correct obvious spelling mistakes, including
"rrot cause" to "root cause". Do not invent incident IDs, values, dates, or
results. The JSON query value must be a concise plain-English search query,
never SQL or an answer. Do not recast an unstructured term such as AWS as an application
unless the user explicitly says it is an application.

Example input: `show unresolved AWS incidents\nFollow-up: show resolved ones`
Example output: {"query":"show resolved AWS incidents"}
"""


def _build_llm(provider: str, api_key: str, model: Optional[str] = None):
    """Returns a LangChain chat model instance for the given provider."""
    provider = (provider or "nvidia").lower()

    if provider == "gemini":
        return _GeminiChat(api_key, model or PROVIDER_DEFAULT_MODELS["gemini"])

    if provider in ("nvidia", "openai", "groq"):
        # NVIDIA NIM, OpenAI, and Groq expose OpenAI-compatible Chat
        # Completions API, so langchain_openai.ChatOpenAI works for either -
        # only the base_url and default model differ.
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            api_key=api_key,
            base_url=PROVIDER_BASE_URLS.get(provider),
            model=model or PROVIDER_DEFAULT_MODELS.get(provider),
            temperature=0.2,
            max_tokens=800,
            timeout=15,
            max_retries=0,
        )

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            api_key=api_key,
            model=model or PROVIDER_DEFAULT_MODELS.get("anthropic"),
            temperature=0.2,
            max_tokens=800,
            timeout=15,
            max_retries=0,
        )

    raise ValueError(f"Unsupported provider: {provider}")


def normalize_question(question: str, api_key: str, provider: str = "groq") -> str:
    """Use the LLM for conversational intent, before governed retrieval."""
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        response = _build_llm(provider, api_key).invoke([
            SystemMessage(content=INTENT_NORMALIZER_PROMPT),
            HumanMessage(content=question),
        ])
        content = response.content if hasattr(response, "content") else str(response)
        if isinstance(content, list):
            content = "".join(str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in content)
        match = re.search(r"\{\s*\"query\"\s*:\s*\"((?:\\.|[^\"])*)\"\s*\}", str(content), re.DOTALL)
        if not match:
            return question
        normalized = json.loads('{"query":"' + match.group(1) + '"}').get("query", "").strip()
        # The deterministic engine consumes natural language, not SQL. Reject
        # a model response that would turn a valid request into bad filters.
        if re.match(r"^(select|with|from|where|match)\b", normalized, flags=re.IGNORECASE):
            return question
        return normalized[:2000] if normalized else question
    except Exception:
        # Intent enhancement must not prevent a deterministic answer.
        return question


def normalize_with_fallback(question: str, api_key: str, provider: str) -> str:
    """Try the primary intent model, then configured provider fallbacks."""
    attempts = [(provider or "gemini", api_key)]
    for configured in configured_provider_keys(preferred_provider=provider):
        candidate = (configured.provider or "gemini", configured.api_key or "")
        if candidate not in attempts:
            attempts.append(candidate)
    for candidate_provider, candidate_key in attempts:
        normalized = normalize_question(question, candidate_key, candidate_provider)
        if normalized != question:
            return normalized
    return question


def _rows_to_context(records: list) -> str:
    if not records:
        return "(no matching incidents found in the dataset)"
    lines = []
    for r in records:
        line = " | ".join(f"{k}={v}" for k, v in r.items() if v not in ("", None))
        lines.append(f"- {line}")
    return "\n".join(lines)


def answer_question(question: str, role: Role, api_key: str, provider: str = "nvidia", model: Optional[str] = None,
                    intent: str = "incident_search", graph_evidence: Optional[list] = None,
                    base_result: Optional[dict] = None) -> dict:
    # Step 1: deterministic retrieval (same engine as the free tier)
    # The LangGraph retrieval node already produced this result. Reusing it
    # avoids a second Pandas scan for every AI response.
    base_result = base_result or dataset_engine.answer_question(question, role)

    # Step 2: ask the LLM to compose the best possible answer from that data
    llm = _build_llm(provider, api_key, model)

    audience_hint = AUDIENCE_HINTS.get(role.detail_level, AUDIENCE_HINTS["raw"])
    system = SYSTEM_PROMPT.format(audience_hint=audience_hint)
    context = _rows_to_context(base_result["data"])

    graph_context = ""
    if graph_evidence:
        graph_context = "\nKnowledge graph evidence (derived from linked incidents):\n" + "\n".join(
            f"- {item.get('root_cause')}: {item.get('incident_count')} incidents; related IDs: {', '.join(item.get('related_incidents', []))}"
            for item in graph_evidence
        )
    user_prompt = (
        f"User intent: {intent}\nQuestion: {question}\n\n"
        f"Authoritative deterministic retrieval result:\n{base_result['answer']}\n\n"
        f"Relevant incident data ({base_result['matched_count']} row(s) matched, "
        f"showing up to {len(base_result['data'])}):\n{context}\n\n"
        "Write the best possible answer to the question using this data. "
        "The UI already renders the matched rows in a table, so summarize the "
        "result in natural language and do not repeat the sample rows. "
        "Use one or two short paragraphs unless the user explicitly requests "
        "a list or incident details."
        + graph_context
    )
    if "FILTER SCOPE:" in question.upper():
        user_prompt += (
            "\n\nCommand Center scope contract: FILTER SCOPE is authoritative. "
            "Answer only about incidents in that selected scope. Do not add "
            "examples, applications, teams, dates, or incident IDs from "
            "outside the retrieved rows."
        )
    if re.search(r"r+o+t\s*cause|explain|why", question, flags=re.IGNORECASE):
        user_prompt += (
            "\n\nExplanation response contract: Explain the leading root cause in natural operational language. "
            "Say what happened, what an engineer should check to confirm it, and the most useful prevention action. "
            "If several causes are relevant, summarize up to three in short paragraphs. Do NOT enumerate sample incident IDs "
            "or repeat the incident table unless the user explicitly asks for a list."
        )
    if re.search(r"\b(detail|details|describe|information about)\b", question, flags=re.IGNORECASE):
        user_prompt += (
            "\n\nIncident-detail response contract: Write a compact operational briefing in one or two natural "
            "paragraphs. Lead with the primary incident that most directly matches the named event, then state "
            "impact, current status, timing, and recorded root cause in complete sentences. If another related "
            "incident exists, mention it briefly as supporting context. Do not use a field-by-field list, parentheses "
            "full of metadata, or a raw incident dump."
        )

    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        response = llm.invoke([
            SystemMessage(content=system),
            HumanMessage(content=user_prompt),
        ])
        answer_text = response.content if hasattr(response, "content") else str(response)
        if isinstance(answer_text, list):
            answer_text = "".join(str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in answer_text)
        # Do not let a model turn an explanation request into a dump of the
        # display sample. The governed explanation already contains the
        # meaning, validation evidence, and preventive action for each cause.
        if re.search(r"r+o+t\s*cause|explain|why", question, flags=re.IGNORECASE) and len(re.findall(r"\bINC-\d+\b", str(answer_text), flags=re.IGNORECASE)) > 2:
            answer_text = base_result["answer"]
        answer_text = str(answer_text).replace("**", "").replace("`", "")
    except Exception as exc:  # noqa: BLE001 - surface a clean error to the API layer
        raise RuntimeError(f"AI provider call failed: {exc}") from exc

    return {
        "answer": answer_text,
        "matched_count": base_result["matched_count"],
        "data": base_result["data"],
        "intent": base_result["intent"],
    }


def answer_with_fallback(question: str, role: Role, api_key: str, provider: str, **kwargs) -> tuple[dict, str]:
    """Try the requested model first, then configured server fallbacks.

    Request-supplied credentials are never silently sent to another vendor.
    Only separately configured server credentials participate in fallback.
    """
    attempts = [(provider or "nvidia", api_key)]
    for configured in configured_provider_keys(preferred_provider=provider):
        candidate = (configured.provider or "nvidia", configured.api_key or "")
        if candidate not in attempts:
            attempts.append(candidate)
    errors = []
    requested_model = kwargs.pop("model", None)
    for candidate_provider, candidate_key in attempts:
        if _PROVIDER_COOLDOWN_UNTIL.get(candidate_provider, 0) > time.monotonic():
            errors.append(f"{candidate_provider}: temporarily cooling down after a recent failure")
            continue
        for candidate_model in provider_model_candidates(candidate_provider, requested_model):
            try:
                result = answer_question(
                    question, role, candidate_key, candidate_provider,
                    model=candidate_model, **kwargs,
                )
                _PROVIDER_COOLDOWN_UNTIL.pop(candidate_provider, None)
                return result, candidate_provider
            except Exception as exc:  # Try the next model, then provider.
                errors.append(f"{candidate_provider}/{candidate_model}: {_safe_provider_error(exc)}")
        _PROVIDER_COOLDOWN_UNTIL[candidate_provider] = time.monotonic() + _PROVIDER_COOLDOWN_SECONDS
    raise RuntimeError("All configured model providers failed: " + " | ".join(errors))
