"""Embedded, free incident relationship graph built from DuckDB facts.

NetworkX runs inside the FastAPI process: no Neo4j server, Docker, Desktop or
cloud account is required. DuckDB is still the durable source of truth; this
module derives a graph for relationship, recurrence and blast-radius analysis.
"""
from collections import Counter
from typing import Any

import networkx as nx

from . import warehouse

_GRAPH: nx.MultiDiGraph | None = None


def _node_id(kind: str, value: object) -> str:
    return f"{kind}:{value or 'Unrecorded'}"


def _build() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    frame = warehouse.query_semantic("SELECT * FROM semantic_incidents")
    for row in frame.fillna("").to_dict(orient="records"):
        incident = _node_id("incident", row["incident_id"])
        graph.add_node(incident, kind="Incident", incident_id=row["incident_id"], title=row["title"], severity=row["severity"], status=row["status"])
        for kind, field, relationship in (
            ("application", "application", "AFFECTS"),
            ("team", "assigned_team", "OWNED_BY"),
            ("environment", "environment", "OCCURRED_IN"),
            ("region", "region", "OCCURRED_IN_REGION"),
            ("root_cause", "root_cause", "HAS_ROOT_CAUSE"),
        ):
            value = row.get(field) or "Unrecorded"
            node = _node_id(kind, value)
            graph.add_node(node, kind=kind.replace("_", " ").title(), name=value)
            graph.add_edge(incident, node, relationship=relationship)
    return graph


def _ensure_graph() -> nx.MultiDiGraph:
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = _build()
    return _GRAPH


def is_configured() -> bool:
    """Compatibility flag: the embedded graph is always available."""
    return True


def status() -> dict[str, Any]:
    graph = _ensure_graph()
    return {"enabled": True, "backend": "networkx", "message": "Embedded local relationship graph is active.", "node_count": graph.number_of_nodes(), "relationship_count": graph.number_of_edges()}


def sync_from_warehouse(limit: int = 10000) -> dict[str, Any]:
    """Rebuild the derived graph after DuckDB data changes."""
    global _GRAPH
    _GRAPH = _build()
    return {"enabled": True, "backend": "networkx", "synced": _GRAPH.number_of_nodes(), "message": "Embedded relationship graph rebuilt from DuckDB."}


def recurring_causes(limit: int = 5) -> list[dict[str, Any]]:
    graph = _ensure_graph()
    causes = []
    for node, attrs in graph.nodes(data=True):
        if attrs.get("kind") != "Root Cause" or attrs.get("name") == "Unrecorded":
            continue
        related = [graph.nodes[source].get("incident_id") for source, _, edge in graph.in_edges(node, data=True) if edge.get("relationship") == "HAS_ROOT_CAUSE"]
        causes.append({"root_cause": attrs["name"], "incident_count": len(related), "related_incidents": related[:5]})
    return sorted(causes, key=lambda item: (-item["incident_count"], item["root_cause"]))[:max(1, min(limit, 20))]


def analytics_summary() -> dict[str, Any]:
    return {**status(), "recurring_causes": recurring_causes()}


def topology(limit_causes: int = 4, limit_incidents_per_cause: int = 4, incident_ids: list[str] | None = None, view: str = "incidents") -> dict[str, Any]:
    """Return a compact relationship subgraph, optionally limited to a query.

    DuckDB interprets a question and supplies its matched incident IDs. This
    projection then renders only their relationships, never global defaults.
    """
    graph = _ensure_graph()
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, str]] = []
    scoped_ids = {str(incident_id) for incident_id in incident_ids or []}
    causes: list[dict[str, Any]] = []
    for node, attrs in graph.nodes(data=True):
        if attrs.get("kind") != "Root Cause" or attrs.get("name") == "Unrecorded":
            continue
        related = [str(graph.nodes[source].get("incident_id")) for source, _, edge in graph.in_edges(node, data=True)
                   if edge.get("relationship") == "HAS_ROOT_CAUSE" and (not scoped_ids or str(graph.nodes[source].get("incident_id")) in scoped_ids)]
        if related:
            causes.append({"root_cause": str(attrs["name"]), "incident_count": len(related), "related_incidents": related})
    selected_causes = sorted(causes, key=lambda item: (-item["incident_count"], item["root_cause"]))[:max(1, limit_causes)]

    if view == "recurrence":
        # An aggregate map answers "recurring causes with linked applications
        # and teams" much better than a dense sample of individual incidents.
        # It is still derived solely from the query-scoped incident IDs.
        selected_applications: set[str] = set()
        app_incidents: dict[str, list[str]] = {}
        for cause in selected_causes:
            cause_id = _node_id("root_cause", cause["root_cause"])
            nodes[cause_id] = {"id": cause_id, "label": cause["root_cause"], "kind": "root_cause", "count": cause["incident_count"]}
            app_counts: Counter[str] = Counter()
            app_members: dict[str, list[str]] = {}
            for incident_id in cause["related_incidents"]:
                incident_node = _node_id("incident", incident_id)
                for _, target, edge in graph.out_edges(incident_node, data=True):
                    if edge.get("relationship") == "AFFECTS":
                        app_name = str(graph.nodes[target].get("name", ""))
                        app_counts[app_name] += 1
                        app_members.setdefault(app_name, []).append(incident_id)
            for app_name, count in app_counts.most_common(2):
                app_id = _node_id("application", app_name)
                nodes[app_id] = {"id": app_id, "label": app_name, "kind": "application", "count": count}
                edges.append({"source": cause_id, "target": app_id, "relationship": "RECURS_IN", "count": count})
                selected_applications.add(app_name)
                app_incidents.setdefault(app_name, []).extend(app_members[app_name])

        for app_name in selected_applications:
            team_counts: Counter[str] = Counter()
            for incident_id in app_incidents[app_name]:
                incident_node = _node_id("incident", incident_id)
                for _, target, edge in graph.out_edges(incident_node, data=True):
                    if edge.get("relationship") == "OWNED_BY":
                        team_counts[str(graph.nodes[target].get("name", ""))] += 1
            app_id = _node_id("application", app_name)
            for team_name, count in team_counts.most_common(2):
                team_id = _node_id("team", team_name)
                nodes[team_id] = {"id": team_id, "label": team_name, "kind": "team", "count": count}
                edges.append({"source": app_id, "target": team_id, "relationship": "OWNED_BY", "count": count})
        return {"nodes": list(nodes.values()), "edges": edges, "scope": {"incident_count": len(scoped_ids) if scoped_ids else None, "is_query_scoped": bool(scoped_ids), "cause_count": len(causes), "view": "recurrence", "description": "Top recurring root causes and their most affected applications and owning teams."}}

    for cause in selected_causes:
        cause_id = _node_id("root_cause", cause["root_cause"])
        nodes[cause_id] = {"id": cause_id, "label": cause["root_cause"], "kind": "root_cause", "count": cause["incident_count"]}
        for incident_id in cause["related_incidents"][:limit_incidents_per_cause]:
            incident_node = _node_id("incident", incident_id)
            attrs = graph.nodes.get(incident_node, {})
            nodes[incident_node] = {"id": incident_node, "label": str(incident_id), "kind": "incident", "severity": str(attrs.get("severity", ""))}
            edges.append({"source": incident_node, "target": cause_id, "relationship": "HAS_ROOT_CAUSE"})
            for _, target, edge in graph.out_edges(incident_node, data=True):
                if edge.get("relationship") not in {"AFFECTS", "OWNED_BY"}:
                    continue
                target_attrs = graph.nodes[target]
                if target_attrs.get("kind") not in {"Application", "Team"}:
                    continue
                nodes[target] = {"id": target, "label": str(target_attrs.get("name", "")), "kind": str(target_attrs["kind"]).lower().replace(" ", "_")}
                edges.append({"source": incident_node, "target": target, "relationship": str(edge["relationship"])})
    return {"nodes": list(nodes.values()), "edges": edges, "scope": {"incident_count": len(scoped_ids) if scoped_ids else None, "is_query_scoped": bool(scoped_ids), "cause_count": len(causes), "view": "incidents"}}
