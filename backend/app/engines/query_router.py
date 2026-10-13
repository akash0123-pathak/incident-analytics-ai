import logging
from typing import Optional

from ..config import get_server_key
from ..roles import get_role
from . import dataset_engine, llm_engine
from .intent_graph import GRAPH

logger = logging.getLogger(__name__)


def handle_query(question: str, role_id: str, request_api_key: Optional[str], request_provider: Optional[str]):
    # Priority: key pasted in the frontend for this request > server-side
    # ("background") key > no key at all -> dataset-only mode.
    api_key = request_api_key
    provider = request_provider

    if not api_key:
        server = get_server_key(preferred_provider=request_provider)
        if server.api_key:
            api_key = server.api_key
            provider = server.provider

    if api_key:
        try:
            # LangGraph makes the decision based on query intent. The model is
            # used only to compose grounded results after deterministic retrieval.
            result = GRAPH.invoke({"question": question, "role_id": role_id, "api_key": api_key, "provider": provider or "nvidia"})["result"]
            result["mode_used"] = "langgraph_ai"
            result["provider"] = result.pop("model_provider", provider or "nvidia")
            return result
        except Exception as exc:  # fall back gracefully instead of erroring the whole request
            # Dataset mode is a first-class, deterministic answer path. Keep
            # provider diagnostics in backend logs and never present vendor
            # errors/model lifecycle messages as part of the user's answer.
            logger.warning("AI provider unavailable; returning dataset result: %s", exc)
            result = GRAPH.invoke({"question": question, "role_id": role_id})["result"]
            result["mode_used"] = "langgraph_dataset"
            result["provider"] = None
            return result

    result = GRAPH.invoke({"question": question, "role_id": role_id})["result"]
    result["mode_used"] = "langgraph_dataset"
    result["provider"] = None
    return result
