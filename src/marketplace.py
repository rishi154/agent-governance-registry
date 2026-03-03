"""
Marketplace core logic:
- aggregate_agents / aggregate_tools: merges live server data with enrichments
- find_similar: keyword-based duplication detection
"""

import json
import re
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional
from src.sqlite_store import sqlite_store

logger = logging.getLogger(__name__)

ENRICHMENTS_PATH = Path(__file__).parent.parent / "data" / "enrichments.json"

COMPLIANCE_OPTIONS = ["PCI-Scoped", "PII-Safe", "Sandbox-Only", "Production-Ready", "Internal-Only"]
STATUS_OPTIONS = ["active", "deprecated", "under-review"]


class EnrichmentStore:
    """
    Reads/writes enrichments.json.
    Keys are item IDs (agent_id for agents, tool name for tools).
    """

    def _load(self) -> dict:
        try:
            if ENRICHMENTS_PATH.exists():
                return json.loads(ENRICHMENTS_PATH.read_text())
        except Exception as e:
            logger.error(f"Failed to load enrichments: {e}")
        return {}

    def _save(self, data: dict):
        ENRICHMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        ENRICHMENTS_PATH.write_text(json.dumps(data, indent=2))

    def get(self, item_id: str) -> dict:
        return self._load().get(item_id, {})

    def save(self, item_id: str, enrichment: dict):
        data = self._load()
        # Merge: keep existing fields not in the new payload so that
        # a re-registration doesn't wipe out fields like example_request.
        existing = data.get(item_id, {})
        data[item_id] = {**existing, **enrichment}
        self._save(data)

    def all(self) -> dict:
        return self._load()


enrichment_store = EnrichmentStore()


def _default_enrichment(name: str, item_type: str) -> dict:
    return {
        "owner_team": "Unassigned",
        "compliance": [],
        "docs_url": "",
        "status": "active",
        "item_type": item_type,
        "registered_at": datetime.utcnow().strftime("%Y-%m-%d"),
    }


def aggregate_agents(raw_agents: list[dict]) -> list[dict]:
    """
    Merge raw A2A agent records with marketplace enrichment metadata.
    Returns unified agent objects ready for the UI.
    """
    enrichments = sqlite_store.all()
    result = []
    for agent in raw_agents:
        agent_id = agent.get("agent_id", "")
        enrichment = enrichments.get(agent_id, _default_enrichment(agent_id, "agent"))
        
        # Prefer enrichment data, fall back to A2A data
        source_repo = enrichment.get("source_repo", "") or agent.get("source_repo", "")
        owner_team = enrichment.get("owner_team", "Unassigned")
        if owner_team == "Unassigned" and agent.get("owner_team"):
            owner_team = agent.get("owner_team")
        
        result.append({
            "id": agent_id,
            "name": _prettify(agent_id),
            "item_type": "agent",
            "agent_type": agent.get("agent_type", ""),
            "capabilities": agent.get("capabilities", []),
            "endpoint": agent.get("endpoint", ""),
            "did": agent.get("did", ""),            # DID from A2A registry
            "owner_team": owner_team,
            "compliance": enrichment.get("compliance", []),
            "docs_url": enrichment.get("docs_url", ""),
            "source_repo": source_repo,
            "status": enrichment.get("status", "active"),
            "registered_at": enrichment.get("registered_at", agent.get("registered_at", "")),
            "description": enrichment.get("description", agent.get("description", "")),
            "ai_review": enrichment.get("ai_review", None),
            "ai_reviewed_at": enrichment.get("ai_reviewed_at", ""),
        })
    return result


def aggregate_tools(raw_tools: list[dict]) -> list[dict]:
    """
    Merge raw MCP tool records with marketplace enrichment metadata.
    Returns unified tool objects ready for the UI.
    """
    enrichments = sqlite_store.all()
    result = []
    for tool in raw_tools:
        tool_id = tool.get("name", "")
        enrichment = enrichments.get(tool_id, _default_enrichment(tool_id, "tool"))
        result.append({
            "id": tool_id,
            "name": _prettify(tool_id),
            "item_type": "tool",
            "description": tool.get("description", enrichment.get("description", "")),
            "parameters": tool.get("parameters", {}),
            "owner_team": enrichment.get("owner_team", "Unassigned"),
            "compliance": enrichment.get("compliance", []),
            "docs_url": enrichment.get("docs_url", ""),
            "source_repo": enrichment.get("source_repo", ""),
            "source_agent": enrichment.get("source_agent", ""),
            # Prefer enrichment endpoint; fall back to endpoint the raw server provided
            "endpoint": enrichment.get("endpoint", "") or tool.get("endpoint", ""),
            "sandbox_endpoint": enrichment.get("sandbox_endpoint", ""),
            "example_request": enrichment.get("example_request", {}),
            "auth_required": enrichment.get("auth_required", False),
            "auth_type": enrichment.get("auth_type", ""),
            "status": enrichment.get("status", "active"),
            "registered_at": enrichment.get("registered_at", ""),
            "ai_review": enrichment.get("ai_review", None),
            "ai_reviewed_at": enrichment.get("ai_reviewed_at", ""),
        })
    return result


def find_similar(name: str, description: str, all_items: list[dict]) -> list[dict]:
    """
    Returns items whose name or description shares significant keyword overlap
    with the provided name+description. Threshold: >40% keyword overlap.
    """
    query_tokens = _tokenize(f"{name} {description}")
    if not query_tokens:
        return []

    matches = []
    for item in all_items:
        item_tokens = _tokenize(f"{item.get('name', '')} {item.get('description', '')} {' '.join(item.get('capabilities', []))}")
        if not item_tokens:
            continue
        overlap = len(query_tokens & item_tokens) / max(len(query_tokens), 1)
        if overlap >= 0.35:
            matches.append({**item, "similarity_score": round(overlap * 100)})

    matches.sort(key=lambda x: x["similarity_score"], reverse=True)
    return matches[:3]  # return top 3 matches


def _tokenize(text: str) -> set:
    """Lowercase, strip punctuation, remove short/common words."""
    STOPWORDS = {"a", "an", "the", "for", "to", "of", "in", "and", "or", "with", "is", "that", "this"}
    tokens = re.findall(r"[a-z]+", text.lower())
    return {t for t in tokens if len(t) > 2 and t not in STOPWORDS}


def _prettify(snake_str: str) -> str:
    """Convert snake_case or hyphen-case to Title Case."""
    return re.sub(r"[_-]", " ", snake_str).title()
