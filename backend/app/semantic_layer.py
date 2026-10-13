"""Business-friendly metrics and governed views for incident analytics."""
from .warehouse import query_semantic

METRICS = {
    "incident_count": "Count of incidents in the selected scope.",
    "open_incident_count": "Incidents whose current status is Open.",
    "critical_incident_count": "Incidents classified as Critical.",
    "average_resolution_hours": "Mean resolution duration for resolved or closed incidents.",
}

DIMENSIONS = ["application", "severity", "status", "category", "assigned_team", "environment", "region"]


def catalog() -> dict:
    return {"view": "semantic_incidents", "metrics": METRICS, "dimensions": DIMENSIONS}


def metric_summary() -> dict:
    frame = query_semantic("""
        SELECT COUNT(*) AS incident_count,
               COUNT(*) FILTER (WHERE lower(status) = 'open') AS open_incident_count,
               COUNT(*) FILTER (WHERE lower(severity) = 'critical') AS critical_incident_count,
               COALESCE(ROUND(AVG(resolution_hours) FILTER (WHERE lower(status) IN ('resolved', 'closed')), 2), 0) AS average_resolution_hours
        FROM semantic_incidents
    """)
    return frame.iloc[0].to_dict()


def breakdown(dimension: str, limit: int = 10) -> list[dict]:
    if dimension not in DIMENSIONS:
        raise ValueError(f"Unknown dimension '{dimension}'. Choose one of: {', '.join(DIMENSIONS)}")
    limit = max(1, min(limit, 100))
    frame = query_semantic(f"""
        SELECT {dimension} AS label, COUNT(*) AS incident_count
        FROM semantic_incidents GROUP BY {dimension}
        ORDER BY incident_count DESC, label ASC LIMIT {limit}
    """)
    return frame.to_dict(orient="records")
