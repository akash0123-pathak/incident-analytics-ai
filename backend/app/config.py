"""
Server-side ("background") configuration.

If you don't want end users pasting an API key into the browser at all,
set one of these environment variables before starting the backend
(e.g. in a .env file loaded by uvicorn, or your shell/deployment secrets):

    NVIDIA_API_KEY=nvapi-...      # NVIDIA NIM (OpenAI-compatible) - default provider
    OPENAI_API_KEY=sk-...         # OpenAI
    ANTHROPIC_API_KEY=sk-ant-...  # Anthropic
    GROQ_API_KEY=gsk_...          # Groq (OpenAI-compatible fallback)

When a server-side key is present, every request automatically gets
AI-powered answers unless the request explicitly forces dataset-only mode.
A key pasted into the frontend Settings panel always takes priority over
the server-side key for that single request.
"""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
    # Never depend on the working directory used to launch uvicorn.  The
    # documented backend/.env is the authoritative local configuration;
    # the optional project-root .env remains a convenient development
    # fallback for older installs. Existing shell secrets still take priority.
    _BACKEND_DIR = Path(__file__).resolve().parent.parent
    load_dotenv(_BACKEND_DIR / ".env")
    load_dotenv(_BACKEND_DIR.parent / ".env")
except ImportError:
    pass

PROVIDER_ENV_MAP = {
    "nvidia": "NVIDIA_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "groq": "GROQ_API_KEY",
    "gemini": "GEMINI_API_KEY",
}

# Base URLs for OpenAI-compatible chat completions endpoints used via LangChain
PROVIDER_BASE_URLS = {
    "nvidia": "https://integrate.api.nvidia.com/v1",
    "openai": None,  # use LangChain / SDK default
    "groq": "https://api.groq.com/openai/v1",
}

PROVIDER_DEFAULT_MODELS = {
    "nvidia": os.getenv("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct"),
    "openai": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    "anthropic": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
    "groq": os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
    "gemini": os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
}

# A model-level retry is useful when a NIM model is retired, capacity-limited,
# or not enabled for a particular NVIDIA account.  Provider-level fallback is
# still used after these candidates are exhausted.
PROVIDER_FALLBACK_MODELS = {
    "nvidia": ["nvidia/llama-3.1-nemotron-70b-instruct"],
}

DEFAULT_PROVIDER = os.getenv("DEFAULT_AI_PROVIDER", "nvidia")


@dataclass
class ServerKeyInfo:
    provider: Optional[str]
    api_key: Optional[str]


def provider_model_candidates(provider: str, requested_model: Optional[str] = None) -> list[str]:
    """Return the configured model followed by compatible, unique fallbacks."""
    if requested_model:
        return [requested_model]
    selected = PROVIDER_DEFAULT_MODELS.get(provider)
    candidates = [selected, *PROVIDER_FALLBACK_MODELS.get(provider, [])]
    return [model for index, model in enumerate(candidates) if model and model not in candidates[:index]]


def get_server_key(preferred_provider: Optional[str] = None) -> ServerKeyInfo:
    """Look for a background/server-side key, preferring `preferred_provider`
    if given, otherwise DEFAULT_PROVIDER, otherwise the first configured one."""
    candidates = []
    if preferred_provider:
        candidates.append(preferred_provider)
    if DEFAULT_PROVIDER not in candidates:
        candidates.append(DEFAULT_PROVIDER)
    candidates.extend([p for p in PROVIDER_ENV_MAP if p not in candidates])

    for provider in candidates:
        env_name = PROVIDER_ENV_MAP.get(provider)
        if env_name and os.getenv(env_name):
            return ServerKeyInfo(provider=provider, api_key=os.getenv(env_name))
    return ServerKeyInfo(provider=None, api_key=None)


def any_server_key_configured() -> bool:
    return any(os.getenv(env_name) for env_name in PROVIDER_ENV_MAP.values())


def configured_provider_keys(preferred_provider: Optional[str] = None) -> list[ServerKeyInfo]:
    """Return configured providers in deterministic primary/fallback order."""
    ordered = []
    # NVIDIA remains primary. Groq is placed ahead of Gemini because the
    # configured Gemini model is currently returning 503 while Groq is
    # healthy; this keeps the natural-language response path responsive.
    for provider in [preferred_provider, DEFAULT_PROVIDER, "nvidia", "groq", "gemini", "openai", "anthropic"]:
        if provider and provider not in ordered:
            ordered.append(provider)
    return [ServerKeyInfo(provider=p, api_key=os.getenv(PROVIDER_ENV_MAP[p])) for p in ordered if os.getenv(PROVIDER_ENV_MAP[p])]
