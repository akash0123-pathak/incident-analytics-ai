from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from .config import any_server_key_configured, get_server_key
from .engines import query_router
from . import auth, knowledge_graph, live_incidents, mcp_client
from .models import AccountLoginRequest, AnalyticsResponse, ConfigResponse, LiveAnalysisRequest, LoginRequest, LoginResponse, QueryRequest, QueryResponse, RegisterRequest
from .roles import list_roles

app = FastAPI(
    title="Incident Analytics AI",
    description="Natural-language incident analytics: dataset-based by default, "
                "AI-powered when an API key (Gemini / NVIDIA / Groq / OpenAI / Anthropic) is provided.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this for production deployments
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "app": "Incident Analytics AI",
        "status": "ok",
        "docs": "/docs",
        "health": "/api/health",
    }


@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)


@app.get("/api/health")
def health():
    return {"status": "ok", "warehouse": "duckdb", "semantic_view": "semantic_incidents", "orchestrator": "langgraph", "knowledge_graph": knowledge_graph.status()}


@app.get("/api/knowledge-graph/status")
def knowledge_graph_status(request: Request):
    auth.require_role(request)
    return knowledge_graph.status()


@app.get("/api/knowledge-graph/topology")
def knowledge_graph_topology(request: Request):
    auth.require_role(request)
    return knowledge_graph.topology()


@app.post("/api/knowledge-graph/sync")
def sync_knowledge_graph(request: Request):
    auth.require_role(request, "engineer")
    return knowledge_graph.sync_from_warehouse()


@app.get("/api/semantic/catalog")
def semantic_catalog():
    return mcp_client.call_tool("get_semantic_catalog")


@app.get("/api/semantic/metrics")
def semantic_metrics():
    return mcp_client.call_tool("get_metric_summary")


@app.get("/api/semantic/breakdown/{dimension}")
def semantic_breakdown(dimension: str, limit: int = 10):
    try:
        return mcp_client.call_tool("get_incident_breakdown", {"dimension": dimension, "limit": limit})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/roles")
def get_roles():
    return list_roles()


@app.post("/api/auth/login", response_model=LoginResponse)
def login(credentials: AccountLoginRequest):
    return auth.account_login(credentials.email, credentials.password)


@app.post("/api/auth/register", response_model=LoginResponse)
def register(credentials: RegisterRequest):
    return auth.register(credentials.email, credentials.password)


@app.post("/api/auth/role-login", response_model=LoginResponse)
def role_login(credentials: LoginRequest):
    return auth.login(credentials.role, credentials.pin)


@app.get("/api/config", response_model=ConfigResponse)
def get_config():
    server = get_server_key()
    metrics = mcp_client.call_tool("get_metric_summary")
    return ConfigResponse(
        server_key_configured=any_server_key_configured(),
        server_provider=server.provider,
        supported_providers=["gemini", "nvidia", "groq", "openai", "anthropic"],
        total_incidents=int(metrics["incident_count"]),
    )


@app.post("/api/query", response_model=QueryResponse)
def query(req: QueryRequest, request: Request):
    auth.require_role(request, req.role)
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")
    try:
        # Follow-up context is supplied by the UI only for references such as
        # "these incidents". Keeping it server-side makes the DuckDB filters
        # and the relationship projection use the identical scope.
        effective_question = f"{req.context_question}\nFollow-up: {req.question}" if req.context_question else req.question
        # All HTTP paths use the same intent-first LangGraph orchestrator.
        if not req.api_key and not get_server_key(preferred_provider=req.provider).api_key:
            result = query_router.handle_query(effective_question, req.role, None, req.provider)
            return QueryResponse(**result)
        result = query_router.handle_query(
            question=effective_question,
            role_id=req.role,
            request_api_key=req.api_key,
            request_provider=req.provider,
        )
        return QueryResponse(**result)
    except (FileNotFoundError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=f"Unable to query incident data: {exc}") from exc
    except Exception as exc:
        # Keep unexpected failures diagnosable without leaking an HTML 500 page to the UI.
        raise HTTPException(status_code=500, detail=f"Incident query failed: {exc}") from exc


@app.get("/api/analytics", response_model=AnalyticsResponse)
def get_analytics(request: Request):
    auth.require_role(request)
    summary = mcp_client.call_tool("get_dashboard_analytics")
    # DuckDB powers standard measures; the embedded graph adds relationship evidence.
    summary["knowledge_graph"] = knowledge_graph.analytics_summary()
    return summary


@app.get("/api/incidents")
def list_incidents(request: Request, role: str = "engineer", limit: int = 50):
    auth.require_role(request, role)
    return mcp_client.call_tool("list_role_incidents", {"role": role, "limit": limit})


@app.post("/api/dataset/reload")
def reload_dataset(request: Request):
    auth.require_role(request, "engineer")
    return mcp_client.call_tool("regenerate_demo_warehouse")


@app.get("/api/live-incidents/status")
def live_incident_status(request: Request):
    """Show whether the read-only Jira Service Management feed is ready."""
    auth.require_role(request)
    return live_incidents.status()


@app.get("/api/live-incidents")
def list_live_incidents(request: Request, limit: int = 25):
    """Read recent JSM incidents without creating or modifying Jira records."""
    auth.require_role(request, "engineer")
    return live_incidents.list_incidents(limit)


@app.post("/api/live-incidents/analyze")
def analyze_live_incidents(payload: LiveAnalysisRequest, request: Request):
    """Analyze the current read-only Jira feed; it never changes Jira records."""
    auth.require_role(request, "engineer")
    return live_incidents.analyze_incidents(payload.question)
