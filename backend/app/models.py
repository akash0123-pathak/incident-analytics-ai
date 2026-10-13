import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


def validate_email(value: str) -> str:
    normalized = value.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
        raise ValueError("Enter a valid email address.")
    return normalized


def validate_password(value: str) -> str:
    if len(value) < 8 or not re.search(r"[A-Z]", value) or not re.search(r"[a-z]", value) or not re.search(r"\d", value) or not re.search(r"[^A-Za-z0-9]", value):
        raise ValueError("Password must be 8+ characters and include uppercase, lowercase, number, and special character.")
    return value


class AccountCredentials(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=8, max_length=128)

    def model_post_init(self, __context: Any) -> None:
        self.email = validate_email(self.email)
        self.password = validate_password(self.password)


class RegisterRequest(AccountCredentials):
    pass


class AccountLoginRequest(AccountCredentials):
    pass


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Natural language question")
    context_question: Optional[str] = Field(default=None, description="Prior question used only for an explicit follow-up reference")
    role: str = Field(default="engineer", description="Role id: engineer | manager | executive")
    api_key: Optional[str] = Field(
        default=None,
        description="Optional per-request API key (sent from the frontend). "
                     "If omitted, the server falls back to a server-side key "
                     "(if configured) or the dataset-only engine.",
    )
    provider: Optional[str] = Field(
        default=None,
        description="'gemini' | 'nvidia' | 'groq' | 'openai' | 'anthropic'. Defaults to server setting.",
    )


class LoginRequest(BaseModel):
    role: str = Field(..., description="engineer | manager | executive")
    pin: str = Field(default="", max_length=32)


class LoginResponse(BaseModel):
    token: str
    role: str
    expires_in: int


class LiveAnalysisRequest(BaseModel):
    question: str = Field(default="Summarize and prioritize the current live incidents.", min_length=1)


class QueryResponse(BaseModel):
    answer: str
    mode_used: str  # "langgraph_ai" | "langgraph_dataset" | legacy modes
    provider: Optional[str] = None
    matched_count: int
    data: List[Dict[str, Any]]
    intent: Optional[Dict[str, Any]] = None
    report: Optional[Dict[str, Any]] = None
    relationship_graph: Optional[Dict[str, Any]] = None


class ConfigResponse(BaseModel):
    server_key_configured: bool
    server_provider: Optional[str]
    supported_providers: List[str]
    total_incidents: int


class AnalyticsResponse(BaseModel):
    total_incidents: int
    open_incidents: int
    critical_incidents: int
    resolved_incidents: int
    average_resolution_hours: float
    incidents_by_month: List[Dict[str, Any]]
    incidents_by_week: List[Dict[str, Any]] = Field(default_factory=list)
    incidents_by_day: List[Dict[str, Any]] = Field(default_factory=list)
    volume_vs_critical_by_day: List[Dict[str, Any]] = Field(default_factory=list)
    sla_breaches_by_day: List[Dict[str, Any]] = Field(default_factory=list)
    incidents_by_application: List[Dict[str, Any]]
    incidents_by_severity: List[Dict[str, Any]]
    recurring_root_causes: List[Dict[str, Any]]
    incidents_by_status: List[Dict[str, Any]]
    incidents_by_team: List[Dict[str, Any]]
    knowledge_graph: Dict[str, Any] = Field(default_factory=dict)
