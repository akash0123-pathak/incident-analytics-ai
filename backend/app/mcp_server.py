"""MCP server exposing governed incident analytics over stdio.

Run: python -m app.mcp_server
Connect a desktop/agent MCP client using the configuration in mcp.json.
"""
from mcp.server.fastmcp import FastMCP

from . import semantic_layer
from .engines import dataset_engine
from .engines.intent_graph import GRAPH
from .roles import get_role

mcp = FastMCP("Incident Analytics Semantic Server")


@mcp.tool()
def get_semantic_catalog() -> dict:
    """List governed incident metrics, dimensions and the semantic view."""
    return semantic_layer.catalog()


@mcp.tool()
def get_metric_summary() -> dict:
    """Get headline incident metrics calculated by the semantic data layer."""
    return semantic_layer.metric_summary()


@mcp.tool()
def get_incident_breakdown(dimension: str, limit: int = 10) -> list[dict]:
    """Break down incident count by an approved business dimension."""
    return semantic_layer.breakdown(dimension, limit)


@mcp.tool()
def ask_incident_analytics(question: str, role: str = "engineer") -> dict:
    """Process a question through the intent-first LangGraph workflow.

    ``role`` is accepted for MCP compatibility but does not choose the path.
    """
    result = GRAPH.invoke({"question": question, "role_id": role})["result"]
    result["mode_used"] = "langgraph_dataset"
    result["provider"] = None
    return result


@mcp.tool()
def get_dashboard_analytics() -> dict:
    """Get the governed incident dashboard metrics and series."""
    return dataset_engine.analytics_summary()


@mcp.tool()
def list_role_incidents(role: str = "engineer", limit: int = 50) -> list[dict]:
    """List recent incidents with the fields permitted for the requested role."""
    df = dataset_engine.load_data()
    role_obj = get_role(role)
    cols = [column for column in role_obj.visible_columns if column in df.columns]
    return df.sort_values("reported_at_dt", ascending=False).head(max(1, min(limit, 100)))[cols].to_dict(orient="records")


@mcp.tool()
def regenerate_demo_warehouse() -> dict:
    """Regenerate the local DuckDB demo warehouse with synthetic incidents."""
    df = dataset_engine.reload_data()
    return {"status": "reloaded", "total_incidents": len(df)}


if __name__ == "__main__":
    mcp.run()
