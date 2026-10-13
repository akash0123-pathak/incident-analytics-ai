"""Transparent natural-language processing used before analytics retrieval.

This is deliberately deterministic NLP (normalisation, entity recognition and
intent classification), rather than an opaque model.  It is auditable and is
also reused by an LLM-enabled route when a provider is configured.
"""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class NlpAnalysis:
    normalized_question: str
    intent: str
    entities: dict


def analyse(question: str) -> NlpAnalysis:
    normalized = " ".join(question.lower().strip().split())
    entities = {}
    incident = re.search(r"\binc\s*-\s*(\d+)\b", normalized)
    if incident:
        entities["incident_id"] = f"INC-{incident.group(1)}"
    if re.search(r"\b(how many|count|number of)\b", normalized):
        intent = "count"
    elif re.search(r"\b(top|most|trend|recurring|root cause)\b", normalized):
        intent = "analysis"
    elif incident:
        intent = "incident_lookup"
    else:
        intent = "incident_search"
    return NlpAnalysis(normalized, intent, entities)
