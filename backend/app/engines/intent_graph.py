"""LangGraph workflow for intent-first incident analytics.

The graph routes on the user's requested job, never on the viewer's job role.
Roles are retained only as a backwards-compatible presentation/privacy option.
"""
import warnings
from typing import Any, TypedDict

# LangGraph's cache module currently instantiates LangChain's serializer while
# importing, without exposing ``allowed_objects`` to application code. Limit
# suppression to that upstream import warning; application deprecations remain
# visible. Remove this when the installed LangGraph release passes the option.
from langchain_core._api.deprecation import LangChainPendingDeprecationWarning

warnings.filterwarnings(
    "ignore",
    message=r"The default value of `allowed_objects` will change.*",
    category=LangChainPendingDeprecationWarning,
    module=r"langgraph\.cache\.base.*",
)

from langgraph.graph import END, START, StateGraph

from .. import knowledge_graph, nlp
from ..roles import get_role
from . import dataset_engine, llm_engine


class QueryState(TypedDict, total=False):
    question: str
    role_id: str
    api_key: str | None
    provider: str | None
    retrieval_question: str
    intent: str
    base_result: dict[str, Any]
    graph_evidence: list[dict[str, Any]]
    result: dict[str, Any]


def classify_intent(state: QueryState) -> QueryState:
    analysis = nlp.analyse(state["question"])
    question = state["question"].lower()
    # The browser retains earlier wording before ``Follow-up:`` only to carry
    # retrieval scope. Visual intent must come from the new request; otherwise
    # a previous "linked applications" query forces a graph onto every reply.
    intent_question = question.rsplit("follow-up:", 1)[-1].strip()
    intent = analysis.intent
    if dataset_engine.wants_report(intent_question):
        intent = "report"
    # A root-cause explanation is a normal answer, not automatically a graph
    # request. Render relationship topology only when the user asks to compare
    # recurring/linked/dependency impact.
    elif any(term in intent_question for term in ("blast radius", "dependency", "related incident", "relationship", "recurring", "linked applications", "linked teams")):
        intent = "relationship_analysis"
    return {"intent": intent}


def route_intent(state: QueryState) -> str:
    return "report" if state["intent"] == "report" else "retrieve"


def retrieve(state: QueryState) -> QueryState:
    # The selected role controls the returned columns and presentation detail.
    # ``get_role`` safely falls back to engineer for an unknown role ID.
    role = get_role(state.get("role_id", "engineer"))
    retrieval_question = state["question"]
    # Normalization is useful only when the browser sends a scoped follow-up.
    # Calling a remote model to rewrite every standalone question adds a full
    # network round trip before the actual answer without improving retrieval.
    if state.get("api_key") and "follow-up:" in retrieval_question.lower():
        retrieval_question = llm_engine.normalize_with_fallback(
            state["question"], state["api_key"], state.get("provider") or "groq"
        )
    result = dataset_engine.answer_question(retrieval_question, role)
    # If structured retrieval found nothing, give the LLM one chance to
    # reinterpret a standalone request before saying there is no data. This
    # keeps DuckDB authoritative while handling wording, spelling and intent.
    if state.get("api_key") and result.get("matched_count", 0) == 0 and "follow-up:" not in retrieval_question.lower():
        interpreted = llm_engine.normalize_with_fallback(
            retrieval_question, state["api_key"], state.get("provider") or "nvidia"
        )
        if interpreted != retrieval_question:
            retrieval_question = interpreted
            result = dataset_engine.answer_question(retrieval_question, role)
    evidence = knowledge_graph.recurring_causes() if state["intent"] == "relationship_analysis" else []
    return {"base_result": result, "graph_evidence": evidence, "retrieval_question": retrieval_question}


def report(state: QueryState) -> QueryState:
    result = dataset_engine.generate_report(state["question"], get_role(state.get("role_id", "engineer")))
    incident_ids = result.pop("_graph_incident_ids", [])
    # Reports get their own scoped, aggregate relationship map so the graph
    # explains the same incident set as the report metrics and evidence table.
    result["relationship_graph"] = knowledge_graph.topology(
        limit_causes=4,
        incident_ids=incident_ids,
        view="recurrence",
    )
    result["intent"] = {**(result.get("intent") or {}), "classified_intent": "report", "orchestration": "langgraph"}
    return {"result": result}


def compose(state: QueryState) -> QueryState:
    base = state["base_result"]
    role = get_role(state.get("role_id", "engineer"))
    if state.get("api_key"):
        result, selected_provider = llm_engine.answer_with_fallback(
            state.get("retrieval_question") or state["question"], role, state["api_key"],
            state.get("provider") or "nvidia", intent=state["intent"], graph_evidence=state.get("graph_evidence", []),
            base_result=base,
        )
        result["model_provider"] = selected_provider
    else:
        result = base
    if state["intent"] == "relationship_analysis":
        # Send a compact topology payload to the UI so relationship answers are
        # visible as a graph, rather than repeated as a text-only count list.
        # The graph must represent the same filtered incident set as the
        # answer, rather than the warehouse-wide recurring-cause ranking.
        incident_ids = base.get("_graph_incident_ids") or [str(row["incident_id"]) for row in base.get("data", []) if row.get("incident_id")]
        question = state["question"].lower()
        recurrence_map = "recurring" in question and ("application" in question or "team" in question)
        result["relationship_graph"] = knowledge_graph.topology(
            limit_causes=5 if recurrence_map else 4,
            incident_ids=incident_ids,
            view="recurrence" if recurrence_map else "incidents",
        )
    # Workflow-only scope metadata must never be exposed in the API response.
    result.pop("_graph_incident_ids", None)
    result["intent"] = {**(result.get("intent") or {}), "classified_intent": state["intent"], "orchestration": "langgraph"}
    return {"result": result}


def build_graph():
    workflow = StateGraph(QueryState)
    workflow.add_node("classify_intent", classify_intent)
    workflow.add_node("retrieve", retrieve)
    workflow.add_node("report", report)
    workflow.add_node("compose", compose)
    workflow.add_edge(START, "classify_intent")
    workflow.add_conditional_edges("classify_intent", route_intent, {"retrieve": "retrieve", "report": "report"})
    workflow.add_edge("retrieve", "compose")
    workflow.add_edge("compose", END)
    workflow.add_edge("report", END)
    return workflow.compile()


GRAPH = build_graph()
