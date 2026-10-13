"""
Role-based access rules.

Every query is answered *through* a role. The role controls:
  - which columns are visible in returned data
  - the level of detail/tone used when composing the answer
  - whether the reporter's identity is shown

This is what makes the assistant "role based" instead of requiring an LLM:
even with zero AI involved, different roles get answers shaped for them.
"""
from dataclasses import dataclass, field
from typing import List


@dataclass
class Role:
    id: str
    label: str
    description: str
    visible_columns: List[str]
    show_reporter: bool
    detail_level: str  # "raw" | "summary" | "executive"


ROLES = {
    "engineer": Role(
        id="engineer",
        label="IT Support Engineer",
        description="Full raw incident detail for troubleshooting and on-call work.",
        visible_columns=[
            "incident_id", "title", "application", "environment", "region",
            "severity", "status", "category", "assigned_team", "reporter",
            "root_cause", "reported_at", "resolved_at", "resolution_hours",
        ],
        show_reporter=True,
        detail_level="raw",
    ),
    "manager": Role(
        id="manager",
        label="Engineering Manager",
        description="Operational ownership and SLA view, without diagnostic or individual details.",
        visible_columns=[
            "incident_id", "title", "application", "severity", "status",
            "assigned_team", "reported_at", "resolution_hours",
        ],
        show_reporter=False,
        detail_level="summary",
    ),
    "executive": Role(
        id="executive",
        label="Executive",
        description="High-level KPIs: counts, critical incidents, and trend direction only.",
        visible_columns=[
            "incident_id", "title", "application", "severity", "status",
            "reported_at",
        ],
        show_reporter=False,
        detail_level="executive",
    ),
}

DEFAULT_ROLE = "engineer"


def get_role(role_id: str) -> Role:
    return ROLES.get(role_id, ROLES[DEFAULT_ROLE])


def list_roles():
    return [
        {"id": r.id, "label": r.label, "description": r.description}
        for r in ROLES.values()
    ]
