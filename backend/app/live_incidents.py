"""Read-only Jira Service Management live incident connector.

The warehouse remains the governed historical source. This connector is a
separate, explicit live view so remote Jira records are never silently mixed
with local demo/history data.
"""
import json
import os
import base64
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .config import get_server_key
from .engines import llm_engine
from .roles import get_role


def status() -> dict[str, Any]:
    site_url = os.getenv("ATLASSIAN_SITE_URL", "").strip()
    email = os.getenv("ATLASSIAN_EMAIL", "").strip()
    token = os.getenv("ATLASSIAN_API_TOKEN", "").strip()
    if not token:
        return {"configured": False, "message": "No Atlassian API token is configured."}
    if not site_url:
        return {"configured": False, "message": "Set ATLASSIAN_SITE_URL to your Jira Cloud URL to enable live incidents."}
    if not email:
        return {"configured": False, "message": "Set ATLASSIAN_EMAIL to use Jira Cloud API-token authentication."}
    if not site_url.startswith("https://") or ".atlassian.net" not in site_url:
        return {"configured": False, "message": "ATLASSIAN_SITE_URL must be an https://<tenant>.atlassian.net URL."}
    return {"configured": True, "site_url": site_url.rstrip("/"), "mode": "read_only"}


def list_incidents(limit: int = 25) -> dict[str, Any]:
    connector = status()
    if not connector["configured"]:
        return {**connector, "incidents": []}
    # Standard Jira fields work across Jira Service Management projects. The
    # result is explicitly read-only and sorted by the latest Jira update.
    query = urllib.parse.urlencode({
        # `projectsWhereType = service_desk` was removed from Jira Cloud JQL.
        # The authenticated account's accessible issues are the live intake
        # scope; callers can inspect the returned project and issue type.
        "jql": "updated >= -365d ORDER BY updated DESC",
        "maxResults": max(1, min(limit, 100)),
        "fields": "summary,status,priority,assignee,reporter,created,updated,labels,issuetype,project",
    })
    # Jira Cloud retired /rest/api/3/search; use its replacement endpoint.
    endpoint = f"{connector['site_url']}/rest/api/3/search/jql?{query}"
    credentials = f"{os.environ.get('ATLASSIAN_EMAIL', '')}:{os.environ['ATLASSIAN_API_TOKEN']}"
    auth_value = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
    request = urllib.request.Request(endpoint, headers={
        # Jira Cloud API tokens are authenticated with Basic auth: email plus
        # API token. Bearer authentication is for OAuth access tokens instead.
        "Authorization": f"Basic {auth_value}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:240]
        return {**connector, "configured": False, "message": f"Atlassian returned HTTP {exc.code}: {detail}", "incidents": []}
    except OSError as exc:
        return {**connector, "configured": False, "message": f"Could not reach Atlassian: {exc}", "incidents": []}
    incidents = []
    for issue in payload.get("issues", []):
        fields = issue.get("fields", {})
        incidents.append({
            "source": "jira_service_management",
            "incident_id": issue.get("key"),
            "title": fields.get("summary"),
            "status": (fields.get("status") or {}).get("name"),
            "priority": (fields.get("priority") or {}).get("name"),
            "type": (fields.get("issuetype") or {}).get("name"),
            "project": (fields.get("project") or {}).get("name"),
            "assignee": (fields.get("assignee") or {}).get("displayName"),
            "reporter": (fields.get("reporter") or {}).get("displayName"),
            "created_at": fields.get("created"),
            "updated_at": fields.get("updated"),
            "labels": fields.get("labels") or [],
        })
    return {**connector, "incidents": incidents, "total": int(payload.get("total", len(incidents)))}


def analyze_incidents(question: str) -> dict[str, Any]:
    """Summarize the current read-only Jira feed with the configured LLM."""
    feed = list_incidents(25)
    if not feed.get("configured"):
        return {**feed, "answer": feed.get("message", "Live incidents are not configured."), "provider": None}
    incidents = feed.get("incidents", [])
    if not incidents:
        return {**feed, "answer": "No live incidents were returned from the configured Jira projects.", "provider": None}
    server = get_server_key()
    if not server.api_key:
        return {**feed, "answer": "Live incidents were fetched, but an AI provider is not configured for analysis.", "provider": None}
    base_result = {
        "answer": f"{len(incidents)} live Jira Service Management incidents were fetched. Analyze only these records.",
        "matched_count": len(incidents),
        "data": incidents,
        "intent": {"source": "live_jira_service_management"},
    }
    result, provider = llm_engine.answer_with_fallback(
        question,
        get_role("engineer"),
        server.api_key,
        server.provider or "nvidia",
        intent="live_incident_analysis",
        base_result=base_result,
    )
    return {**feed, "answer": result["answer"], "provider": provider}
