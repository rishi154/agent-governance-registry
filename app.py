"""
Agent Marketplace — Demo Application
Aggregates agents (A2A server) and tools (MCP server) into a governed marketplace UI.
Run: python app.py  →  http://localhost:8000
"""

import json
import logging
import shutil
import httpx
import uvicorn
import asyncio
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, field_validator
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load .env before importing any module that reads env vars (governance_agent, etc.)
try:
    from dotenv import load_dotenv
    _env = Path(__file__).parent / ".env"
    if _env.exists():
        load_dotenv(_env)
        logger.info(f"Loaded env from {_env}")
    else:
        load_dotenv()  # search up from cwd
except ImportError:
    pass

from src.clients import MCPClient, A2AClient
from src.marketplace import (
    aggregate_agents, aggregate_tools,
    find_similar, COMPLIANCE_OPTIONS
)
from src.sqlite_store import sqlite_store
from src.auth import verify_api_key, require_permission, optional_auth, ALLOW_UNAUTHENTICATED_READ

from src.governance_agent import governance_agent  # must be after load_dotenv()

app = FastAPI(title="Agent Marketplace", version="1.0.0")
mcp = MCPClient()
a2a = A2AClient()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class RegisterAgentRequest(BaseModel):
    agent_id: str
    agent_type: str
    endpoint: str
    capabilities: list[str] = []
    owner_team: str
    compliance: list[str] = []
    docs_url: str = ""
    source_repo: str          # required — must be a valid URL
    description: str = ""

    @field_validator("source_repo")
    @classmethod
    def source_repo_must_be_url(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("source_repo is required — provide the git repository URL")
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("source_repo must be a valid URL starting with http:// or https://")
        return v

class RegisterToolRequest(BaseModel):
    tool_id: str
    description: str
    owner_team: str
    compliance: list[str] = []
    docs_url: str = ""
    source_repo: str              # required — must be a valid URL
    source_agent: str = ""        # agent_id that provides this tool

    @field_validator("source_repo")
    @classmethod
    def source_repo_must_be_url(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("source_repo is required — provide the git repository URL")
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("source_repo must be a valid URL starting with http:// or https://")
        return v
    endpoint: str = ""            # production HTTP endpoint
    sandbox_endpoint: str = ""    # safe endpoint for Try It Live (never call prod by accident)
    example_request: dict = {}    # sample payload shown in the Try It panel
    auth_required: bool = False   # whether callers must supply auth headers
    auth_type: str = ""           # hint: "bearer", "api_key", "basic"


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.get("/api/stats")
async def get_stats(auth: tuple = Depends(optional_auth)):
    role, actor = auth
    agents = aggregate_agents(await a2a.get_agents())
    tools = aggregate_tools(await _get_all_tools())
    all_items = agents + tools
    teams = {i["owner_team"] for i in all_items if i["owner_team"] != "Unassigned"}
    active = sum(1 for i in all_items if i.get("status") in ["active", "approved"])
    health_pct = round((active / len(all_items) * 100) if all_items else 0)
    return {
        "total_agents": len(agents),
        "total_tools": len(tools),
        "total_teams": len(teams),
        "health_pct": health_pct,
        "mcp_online": await mcp.is_healthy(),
        "a2a_online": await a2a.is_healthy(),
        "governance_online": governance_agent.model is not None,
        "enforcement": {
            "approved": sum(1 for i in all_items if i.get("status") in ["active", "approved"]),
            "blocked": sum(1 for i in all_items if i.get("status") in ["rejected", "pending_review", "under_review"]),
        },
    }


@app.get("/api/governance/status")
async def governance_status():
    """Returns whether the AI governance agent is configured and ready."""
    import os
    ready = governance_agent.model is not None
    return {
        "ready": ready,
        "model": os.getenv("VERTEX_CLAUDE_MODEL", "claude-opus-4-5@20251101") if ready else None,
        "project": os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or "(not set)",
        "region":  os.getenv("GCP_LOCATION")   or os.getenv("VERTEX_REGION", "us-east5"),
        "hint": None if ready else (
            "Set GCP_PROJECT_ID and GCP_LOCATION in your .env file, "
            "then restart the marketplace. "
            "Also ensure: gcloud auth application-default login"
        ),
    }


@app.post("/api/demo/reset")
async def demo_reset():
    """
    Resets the marketplace to the clean demo baseline.
    Restores enrichments.json from data/enrichments.baseline.json.
    FOR DEMO USE ONLY — wipes all current enrichments including AI reviews.
    """
    baseline = Path(__file__).parent / "data" / "enrichments.baseline.json"
    target   = Path(__file__).parent / "data" / "enrichments.json"
    if not baseline.exists():
        raise HTTPException(status_code=404, detail="enrichments.baseline.json not found")
    shutil.copy2(baseline, target)
    data = json.loads(target.read_text())
    agents = [k for k, v in data.items() if v.get("item_type") == "agent"]
    tools  = [k for k, v in data.items() if v.get("item_type") == "tool"]
    logger.info(f"Demo reset: {len(agents)} agents, {len(tools)} tools from baseline")
    return {
        "status": "reset",
        "agents": agents,
        "tools": tools,
        "message": f"Reset to baseline: {len(agents)} agent(s), {len(tools)} tool(s). Restart the A2A server for a fully clean agent registry.",
    }


@app.get("/api/agents")
async def get_agents(auth: tuple = Depends(optional_auth)):
    role, actor = auth
    raw = await a2a.get_agents()
    agents = aggregate_agents(raw)
    
    # Show all agents regardless of status (for demo)
    return agents


@app.get("/api/tools")
async def get_tools(auth: tuple = Depends(optional_auth)):
    role, actor = auth
    raw = await _get_all_tools()
    return aggregate_tools(raw)


@app.get("/api/search")
async def search(q: str = ""):
    if not q.strip():
        return []
    agents = aggregate_agents(await a2a.get_agents())
    tools = aggregate_tools(await _get_all_tools())
    all_items = agents + tools
    q_lower = q.lower()
    results = []
    for item in all_items:
        searchable = " ".join([
            item.get("name", ""),
            item.get("description", ""),
            item.get("owner_team", ""),
            item.get("agent_type", ""),
            " ".join(item.get("capabilities", [])),
            " ".join(item.get("compliance", [])),
        ]).lower()
        if q_lower in searchable:
            results.append(item)
    return results


@app.get("/api/similarity")
async def similarity(name: str = "", description: str = ""):
    agents = aggregate_agents(await a2a.get_agents())
    tools = aggregate_tools(await _get_all_tools())
    return find_similar(name, description, agents + tools)


@app.post("/api/register/agent")
async def register_agent(req: RegisterAgentRequest, auth: tuple = Depends(require_permission("can_register"))):
    role, actor = auth
    
    # Check if agent already has enrichment (from auto-detection or previous registration)
    existing_enrichment = sqlite_store.get(req.agent_id)
    
    payload = {
        "agent_id": req.agent_id,
        "agent_type": req.agent_type,
        "endpoint": req.endpoint,
        "did": f"did:key:z6Mk{req.agent_id.replace('_', '')}",
        "public_key": "marketplace-registered-key",
        "capabilities": req.capabilities,
    }
    already_existed = False
    try:
        await a2a.register_agent(payload)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 400 and "already registered" in e.response.text:
            already_existed = True
            logger.info(f"Agent {req.agent_id} already in A2A registry — updating enrichment only")
        else:
            raise HTTPException(status_code=502, detail=f"A2A server error: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"A2A server error: {e}")

    # Merge with existing enrichment to preserve auto-detected governance review
    new_enrichment = {
        "owner_team": req.owner_team,
        "compliance": req.compliance,
        "docs_url": req.docs_url,
        "source_repo": req.source_repo,
        "status": "pending_review",  # Always pending until approved
        "item_type": "agent",
        "description": req.description,
        "registered_at": existing_enrichment.get("registered_at") if existing_enrichment else datetime.utcnow().strftime("%Y-%m-%d"),
        "discovery_method": "marketplace",  # Mark as marketplace registration
    }
    
    # Preserve existing AI review if present (don't overwrite auto-detected review)
    if existing_enrichment and existing_enrichment.get("ai_review"):
        logger.info(f"Preserving existing AI review for {req.agent_id}")
        new_enrichment["ai_review"] = existing_enrichment["ai_review"]
        new_enrichment["ai_reviewed_at"] = existing_enrichment["ai_reviewed_at"]
    
    sqlite_store.save(req.agent_id, new_enrichment)
    sqlite_store.log_action(req.agent_id, "registered", actor, {"method": "marketplace"})

    # Run AI governance review (only if not already reviewed)
    review = new_enrichment.get("ai_review")  # Use existing review if present
    if not review:
        try:
            catalog = aggregate_agents(await a2a.get_agents()) + aggregate_tools(await _get_all_tools())
            source_code = await governance_agent.fetch_source_code(req.source_repo)
            review = await governance_agent.review(
                item_id=req.agent_id,
                item_type="agent",
                payload=req.model_dump(),
                existing_catalog=catalog,
                source_code=source_code,
            )
            if review:
                has_issues = review.get("requires_human_review") or (review.get("risk_flags") and len(review.get("risk_flags")) > 0)
                new_status = "under_review" if has_issues else "pending_review"
                sqlite_store.save(req.agent_id, {
                    "ai_review": review,
                    "ai_reviewed_at": datetime.utcnow().strftime("%Y-%m-%d"),
                    "status": new_status,
                })
                sqlite_store.log_action(req.agent_id, "ai_review_completed", "system", {"confidence": review.get("confidence")})
        except Exception as e:
            logger.warning(f"Governance review failed for {req.agent_id}: {e}")

    return {
        "status": "updated" if already_existed or existing_enrichment else "registered",
        "agent_id": req.agent_id,
        "ai_review": review,
        "note": "Preserved existing governance review" if existing_enrichment and existing_enrichment.get("ai_review") else None,
        "approval_required": True,
    }


@app.post("/api/register/tool")
async def register_tool(req: RegisterToolRequest, auth: tuple = Depends(require_permission("can_register"))):
    role, actor = auth
    
    sqlite_store.save(req.tool_id, {
        "owner_team": req.owner_team,
        "compliance": req.compliance,
        "docs_url": req.docs_url,
        "source_repo": req.source_repo,
        "source_agent": req.source_agent,
        "endpoint": req.endpoint,
        "sandbox_endpoint": req.sandbox_endpoint,
        "example_request": req.example_request,
        "auth_required": req.auth_required,
        "auth_type": req.auth_type,
        "status": "pending_review",
        "item_type": "tool",
        "description": req.description,
        "registered_at": datetime.utcnow().strftime("%Y-%m-%d"),
    })
    sqlite_store.log_action(req.tool_id, "registered", actor, {"method": "marketplace"})

    # Run AI governance review
    review = None
    try:
        catalog = aggregate_agents(await a2a.get_agents()) + aggregate_tools(await _get_all_tools())
        source_code = await governance_agent.fetch_source_code(req.source_repo)
        review = await governance_agent.review(
            item_id=req.tool_id,
            item_type="tool",
            payload=req.model_dump(),
            existing_catalog=catalog,
            source_code=source_code,
        )
        if review:
            has_issues = review.get("requires_human_review") or (review.get("risk_flags") and len(review.get("risk_flags")) > 0)
            new_status = "under_review" if has_issues else "pending_review"
            sqlite_store.save(req.tool_id, {
                "ai_review": review,
                "ai_reviewed_at": datetime.utcnow().strftime("%Y-%m-%d"),
                "status": new_status,
            })
            sqlite_store.log_action(req.tool_id, "ai_review_completed", "system", {"confidence": review.get("confidence")})
    except Exception as e:
        logger.warning(f"Governance review failed for {req.tool_id}: {e}")

    return {"status": "registered", "tool_id": req.tool_id, "ai_review": review, "approval_required": True}


@app.get("/api/agent/{agent_id}/tools")
async def get_agent_tools(agent_id: str, auth: tuple = Depends(optional_auth)):
    """Return all tools that belong to a specific agent."""
    role, actor = auth
    all_tools = aggregate_tools(await _get_all_tools())
    return [t for t in all_tools if t.get("source_agent") == agent_id]


# ---------------------------------------------------------------------------
# Approval Workflow
# ---------------------------------------------------------------------------

class ApprovalRequest(BaseModel):
    decision: str  # "approve" or "reject"
    notes: str = ""

@app.get("/api/review-queue")
async def get_review_queue(auth: tuple = Depends(require_permission("can_approve"))):
    """Get all agents/tools pending review (admin only)."""
    role, actor = auth
    
    agents = aggregate_agents(await a2a.get_agents())
    tools = aggregate_tools(await _get_all_tools())
    all_items = agents + tools
    
    # Filter to pending/under review
    pending = [i for i in all_items if i.get("status") in ["pending_review", "under_review"]]
    
    return {
        "count": len(pending),
        "items": pending
    }

@app.post("/api/agents/{agent_id}/approve")
async def approve_agent(agent_id: str, req: ApprovalRequest, auth: tuple = Depends(require_permission("can_approve"))):
    """Approve or reject an agent (admin only)."""
    role, actor = auth
    
    if req.decision not in ["approve", "reject"]:
        raise HTTPException(status_code=400, detail="Decision must be 'approve' or 'reject'")
    
    # Check agent exists
    agent = sqlite_store.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    
    # Update status
    new_status = "approved" if req.decision == "approve" else "rejected"
    sqlite_store.update_status(agent_id, new_status, actor)
    sqlite_store.log_action(agent_id, f"agent_{req.decision}d", actor, {"notes": req.notes})
    
    logger.info(f"Agent {agent_id} {req.decision}d by {actor}")
    
    return {
        "status": "success",
        "agent_id": agent_id,
        "decision": req.decision,
        "new_status": new_status
    }

@app.get("/api/agents/{agent_id}/audit")
async def get_agent_audit(agent_id: str, auth: tuple = Depends(require_permission("can_approve"))):
    """Get audit log for an agent (admin only)."""
    role, actor = auth
    return sqlite_store.get_audit_log(agent_id=agent_id)


# ---------------------------------------------------------------------------
# Existing endpoints
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Enforcement helpers
# ---------------------------------------------------------------------------

BLOCKED_STATUSES = {"rejected", "pending_review", "under_review"}

def _check_enforcement(item_id: str, item_type: str = "agent") -> dict | None:
    """Return enrichment if item is approved/active, else raise 403."""
    enr = sqlite_store.get(item_id)
    status = enr.get("status", "pending_review") if enr else "pending_review"
    if status in BLOCKED_STATUSES:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "blocked_by_governance",
                "item_id": item_id,
                "item_type": item_type,
                "status": status,
                "message": f"{item_type.title()} '{item_id}' is not approved. Current status: {status}. "
                           f"An admin must approve it before it can be invoked.",
            },
        )
    return enr


@app.get("/api/agents/{agent_id}/enforcement")
async def get_enforcement_status(agent_id: str):
    """Check whether an agent is approved and allowed to receive traffic.
    
    Designed to be called by A2A servers, gateways, or any consumer
    before routing messages to an agent.
    
    Returns:
        {"agent_id": ..., "allowed": true/false, "status": ..., "reason": ...}
    """
    enr = sqlite_store.get(agent_id)
    status = enr.get("status", "unknown") if enr else "unknown"
    allowed = status not in BLOCKED_STATUSES and status != "unknown"
    
    reason = None
    if not enr:
        reason = "Agent not registered in marketplace"
    elif status in BLOCKED_STATUSES:
        reason = f"Agent status is '{status}' — admin approval required"
    
    return {
        "agent_id": agent_id,
        "allowed": allowed,
        "status": status,
        "reason": reason,
        "reviewed": bool(enr.get("ai_review")) if enr else False,
    }


@app.get("/api/enforcement/summary")
async def enforcement_summary(auth: tuple = Depends(optional_auth)):
    """Summary of all agents/tools and their enforcement status."""
    enrichments = sqlite_store.all()
    summary = {"approved": 0, "blocked": 0, "pending": 0, "items": []}
    for item_id, enr in enrichments.items():
        status = enr.get("status", "unknown")
        allowed = status not in BLOCKED_STATUSES and status != "unknown"
        bucket = "approved" if allowed else ("pending" if status in {"pending_review", "under_review"} else "blocked")
        summary[bucket] += 1
        summary["items"].append({
            "id": item_id,
            "type": enr.get("item_type", "unknown"),
            "status": status,
            "allowed": allowed,
        })
    return summary


# ---------------------------------------------------------------------------
# Proxy & Invoke (with enforcement)
# ---------------------------------------------------------------------------

class ProxyRequest(BaseModel):
    endpoint: str
    payload: dict = {}
    headers: dict = {}    # caller-supplied headers (Authorization, X-API-Key, etc.)
    tool_id: str = ""     # optional — if provided, enforcement is checked

@app.post("/api/proxy")
async def proxy_tool_call(req: ProxyRequest):
    """Forward a test call to a tool endpoint. Enforces governance approval."""
    # Enforce governance if tool_id provided
    if req.tool_id:
        _check_enforcement(req.tool_id, "tool")
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(req.endpoint, json=req.payload, headers=req.headers)
            return {"status": resp.status_code, "response": resp.json()}
    except Exception as e:
        return {"status": 0, "error": str(e)}


class InvokeAgentRequest(BaseModel):
    agent_id: str
    capability: str
    payload: dict = {}

@app.post("/api/invoke-agent")
async def invoke_agent(req: InvokeAgentRequest):
    """Send an A2A-format message to an agent. Blocked if agent is not approved."""
    # Enforce governance — reject if not approved
    _check_enforcement(req.agent_id, "agent")
    
    raw_agents = await a2a.get_agents()
    agent = next((a for a in raw_agents if a.get("agent_id") == req.agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{req.agent_id}' not found in A2A registry")

    endpoint = agent.get("endpoint", "")
    did = agent.get("did", f"did:key:z6Mk{req.agent_id.replace('_', '')}")

    a2a_message = {
        "from_did": "did:key:marketplace-demo",
        "to_did": did,
        "message_type": req.capability,
        "body": req.payload,
        "signature": "marketplace-demo-sig",
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(endpoint, json=a2a_message)
            return {
                "status": resp.status_code,
                "a2a_message_sent": a2a_message,
                "response": resp.json(),
            }
    except Exception as e:
        return {"status": 0, "error": str(e)}



# ---------------------------------------------------------------------------
# Helper: combine MCP tools + enrichment-only tools
# ---------------------------------------------------------------------------

async def _get_all_tools() -> list[dict]:
    """Merge live MCP tools with tools that exist only in enrichments (demo tools)."""
    live_tools = await mcp.get_tools()
    live_ids = {t.get("name", "") for t in live_tools}

    enrichments = sqlite_store.all()
    enrichment_tools = []
    for eid, enr in enrichments.items():
        if enr.get("item_type") == "tool" and eid not in live_ids:
            enrichment_tools.append({
                "name": eid,
                "description": enr.get("description", ""),
                "parameters": {},
            })

    return live_tools + enrichment_tools


# ---------------------------------------------------------------------------
# UI — single page HTML
# ---------------------------------------------------------------------------

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Agent Marketplace</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    .badge-pci    { background:#fef3c7; color:#92400e; }
    .badge-pii    { background:#dbeafe; color:#1e40af; }
    .badge-prod   { background:#d1fae5; color:#065f46; }
    .badge-sandbox{ background:#f3e8ff; color:#6b21a8; }
    .badge-internal{background:#f1f5f9; color:#475569; }
    .dot-active   { background:#22c55e; }
    .dot-deprecated{background:#ef4444;}
    .dot-review   { background:#f59e0b; }
    .card-agent   { border-left: 4px solid #6366f1; }
    .card-tool    { border-left: 4px solid #0ea5e9; }
    .card-blocked { opacity: 0.7; }
    .badge-blocked{ background:#fee2e2; color:#991b1b; }
    .badge-approved{ background:#d1fae5; color:#065f46; }
    .similar-warn { background:#fffbeb; border:1px solid #f59e0b; }
  </style>
</head>
<body class="bg-gray-50 min-h-screen font-sans">

<!-- HEADER -->
<header class="bg-indigo-900 text-white shadow-lg">
  <div class="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
    <div class="flex items-center gap-3">
      <svg class="w-8 h-8 text-indigo-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
          d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"/>
      </svg>
      <div>
        <h1 class="text-xl font-bold tracking-tight">Agent Marketplace</h1>
        <p class="text-indigo-300 text-xs">Enterprise Agentic AI Registry &amp; Governance</p>
      </div>
    </div>
    <!-- Stats bar -->
    <div id="statsBar" class="flex gap-6 text-sm">
      <div class="text-center"><div id="statAgents" class="text-2xl font-bold">-</div><div class="text-indigo-300 text-xs">Agents</div></div>
      <div class="text-center"><div id="statTools"  class="text-2xl font-bold">-</div><div class="text-indigo-300 text-xs">Tools</div></div>
      <div class="text-center"><div id="statTeams"  class="text-2xl font-bold">-</div><div class="text-indigo-300 text-xs">Teams</div></div>
      <div class="text-center"><div id="statHealth" class="text-2xl font-bold">-</div><div class="text-indigo-300 text-xs">Health</div></div>
    </div>
  </div>
  <!-- Server status -->
  <div class="max-w-7xl mx-auto px-6 pb-2 flex gap-4 text-xs">
    <span>MCP Server: <span id="mcpStatus" class="font-semibold">checking...</span></span>
    <span>A2A Server: <span id="a2aStatus" class="font-semibold">checking...</span></span>
  </div>
</header>

<!-- MAIN -->
<div class="max-w-7xl mx-auto px-6 py-6 flex gap-6">

  <!-- SIDEBAR -->
  <aside class="w-56 shrink-0">
    <div class="bg-white rounded-xl shadow-sm p-4 mb-4">
      <p class="text-xs font-semibold text-gray-500 uppercase mb-2">Browse</p>
      <button onclick="switchTab('agents')" id="tabAgents"
        class="tab-btn w-full text-left px-3 py-2 rounded-lg text-sm font-medium mb-1 bg-indigo-50 text-indigo-700">
        🤖 Agents
      </button>
      <button onclick="switchTab('tools')" id="tabTools"
        class="tab-btn w-full text-left px-3 py-2 rounded-lg text-sm font-medium text-gray-600 hover:bg-gray-50">
        🔧 Tools
      </button>
    </div>

    <div class="bg-white rounded-xl shadow-sm p-4 mb-4">
      <p class="text-xs font-semibold text-gray-500 uppercase mb-2">Filter</p>
      <label class="text-xs text-gray-500 block mb-1">Team</label>
      <select id="filterTeam" onchange="applyFilters()"
        class="w-full text-sm border border-gray-200 rounded-lg px-2 py-1.5 mb-3">
        <option value="">All Teams</option>
      </select>
      <label class="text-xs text-gray-500 block mb-1">Compliance</label>
      <select id="filterCompliance" onchange="applyFilters()"
        class="w-full text-sm border border-gray-200 rounded-lg px-2 py-1.5 mb-3">
        <option value="">All</option>
        <option>PCI-Scoped</option>
        <option>PII-Safe</option>
        <option>Production-Ready</option>
        <option>Sandbox-Only</option>
        <option>Internal-Only</option>
      </select>
      <label class="text-xs text-gray-500 block mb-1">Status</label>
      <select id="filterStatus" onchange="applyFilters()"
        class="w-full text-sm border border-gray-200 rounded-lg px-2 py-1.5">
        <option value="">All</option>
        <option value="active">Active</option>
        <option value="under-review">Under Review</option>
        <option value="deprecated">Deprecated</option>
      </select>
    </div>

  </aside>

  <!-- CONTENT -->
  <main class="flex-1 min-w-0">
    <!-- Search + Register -->
    <div class="flex gap-3 mb-5">
      <div class="relative flex-1">
        <input id="searchInput" type="text" placeholder="Search agents, tools, teams, capabilities..."
          oninput="handleSearch(this.value)"
          class="w-full pl-10 pr-4 py-2.5 bg-white border border-gray-200 rounded-xl shadow-sm text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"/>
        <svg class="absolute left-3 top-3 w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-4.35-4.35M17 11A6 6 0 105 11a6 6 0 0012 0z"/>
        </svg>
      </div>
      <button onclick="openRegisterPanel()"
        class="flex items-center gap-2 bg-indigo-600 text-white text-sm font-medium px-4 py-2.5 rounded-xl hover:bg-indigo-700 shadow-sm transition">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
        </svg>
        Register New
      </button>
    </div>

    <!-- Empty / loading state -->
    <div id="emptyState" class="hidden text-center py-16 text-gray-400">
      <svg class="w-12 h-12 mx-auto mb-3 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/>
      </svg>
      <p class="text-sm font-medium">No items found</p>
      <p class="text-xs mt-1">Use the search bar or switch tabs to browse agents and tools</p>
    </div>

    <!-- Card grid -->
    <div id="cardGrid" class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4"></div>
  </main>
</div>

<!-- DETAIL PANEL (slide-in) -->
<div id="detailOverlay" class="hidden fixed inset-0 bg-black/40 z-40" onclick="closeDetail()"></div>
<div id="detailPanel" class="fixed right-0 top-0 h-full w-96 bg-white shadow-2xl z-50 translate-x-full transition-transform duration-300 overflow-y-auto">
  <div class="p-6">
    <button onclick="closeDetail()" class="float-right text-gray-400 hover:text-gray-600">
      <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
      </svg>
    </button>
    <div id="detailContent"></div>
  </div>
</div>

<!-- REGISTER PANEL (slide-in) -->
<div id="registerOverlay" class="hidden fixed inset-0 bg-black/40 z-40" onclick="closeRegister()"></div>
<div id="registerPanel" class="fixed right-0 top-0 h-full w-[480px] bg-white shadow-2xl z-50 translate-x-full transition-transform duration-300 overflow-y-auto">
  <div class="p-6">
    <button onclick="closeRegister()" class="float-right text-gray-400 hover:text-gray-600">
      <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
      </svg>
    </button>
    <h2 class="text-lg font-bold text-gray-800 mb-1">Register New</h2>
    <p class="text-sm text-gray-500 mb-5">Add a new agent or tool to the marketplace.</p>

    <!-- Similarity warning -->
    <div id="similarWarn" class="hidden similar-warn rounded-xl p-3 mb-4">
      <p class="text-sm font-semibold text-amber-800 mb-1">⚠️ Similar items already exist</p>
      <div id="similarList" class="space-y-1"></div>
    </div>

    <form id="registerForm" onsubmit="submitRegister(event)" class="space-y-4">
      <div>
        <label class="text-xs font-semibold text-gray-600 block mb-1">Type *</label>
        <div class="flex gap-3">
          <label class="flex items-center gap-2 text-sm cursor-pointer">
            <input type="radio" name="regType" value="agent" checked onchange="toggleRegType()"> Agent
          </label>
          <label class="flex items-center gap-2 text-sm cursor-pointer">
            <input type="radio" name="regType" value="tool" onchange="toggleRegType()"> Tool
          </label>
        </div>
      </div>

      <div>
        <label class="text-xs font-semibold text-gray-600 block mb-1">Name / ID *</label>
        <input id="regId" type="text" placeholder="e.g. fraud_risk_scorer"
          oninput="checkSimilarity()"
          class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"/>
        <p class="text-xs text-gray-400 mt-1">Use lowercase with underscores</p>
      </div>

      <div>
        <label class="text-xs font-semibold text-gray-600 block mb-1">Description *</label>
        <textarea id="regDescription" rows="3" placeholder="What does this agent/tool do?"
          oninput="checkSimilarity()"
          class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"></textarea>
      </div>

      <div>
        <label class="text-xs font-semibold text-gray-600 block mb-1">Owner Team *</label>
        <input id="regTeam" type="text" placeholder="e.g. Risk & Fraud"
          class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"/>
      </div>

      <!-- Agent-only fields -->
      <div id="agentFields">
        <div class="mb-4">
          <label class="text-xs font-semibold text-gray-600 block mb-1">Agent Type</label>
          <input id="regAgentType" type="text" placeholder="e.g. risk, compliance, onboarding"
            class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"/>
        </div>
        <div class="mb-4">
          <label class="text-xs font-semibold text-gray-600 block mb-1">Capabilities</label>
          <input id="regCapabilities" type="text" placeholder="comma-separated: fraud_scoring, aml_check"
            class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"/>
        </div>
        <div>
          <label class="text-xs font-semibold text-gray-600 block mb-1">Endpoint URL</label>
          <input id="regEndpoint" type="text" placeholder="http://localhost:8100/receive"
            class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"/>
        </div>
      </div>

      <div>
        <label class="text-xs font-semibold text-gray-600 block mb-1">Compliance Tags</label>
        <div id="complianceTags" class="flex flex-wrap gap-2">
          <!-- rendered by JS -->
        </div>
      </div>

      <div>
        <label class="text-xs font-semibold text-gray-600 block mb-1">Docs URL</label>
        <input id="regDocs" type="text" placeholder="https://wiki.internal/..."
          class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"/>
      </div>

      <div>
        <label class="text-xs font-semibold text-gray-600 block mb-1">Source Code Repository <span class="text-red-500">*</span></label>
        <input id="regSourceRepo" type="url" placeholder="https://github.com/your-org/repo" required
          class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"/>
        <p class="text-xs text-gray-400 mt-1">Required — AI governance review fetches code from this URL to validate compliance claims.</p>
      </div>

      <div id="regError" class="hidden text-sm text-red-600 bg-red-50 rounded-lg p-3"></div>
      <div id="regSuccess" class="hidden text-sm text-green-700 bg-green-50 rounded-lg p-3"></div>

      <button type="submit"
        class="w-full bg-indigo-600 text-white font-semibold py-2.5 rounded-xl hover:bg-indigo-700 transition text-sm">
        Register
      </button>
    </form>
  </div>
</div>

<!-- SEED MODAL -->

<script>
// ============================================================
// STATE
// ============================================================
let allAgents = [];
let allTools  = [];
let currentTab = 'agents';
let searchTimeout = null;
let similarTimeout = null;
let selectedCompliance = new Set();
const agentToolsCache = {};  // agentId -> tool list, populated when agent detail opens

// ============================================================
// INIT
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
  renderComplianceTags();
  loadAll();
});

async function loadAll() {
  await Promise.all([loadStats(), loadAgents(), loadTools()]);
}

async function loadStats() {
  try {
    const s = await api('/api/stats');
    document.getElementById('statAgents').textContent = s.total_agents;
    document.getElementById('statTools').textContent  = s.total_tools;
    document.getElementById('statTeams').textContent  = s.total_teams;
    document.getElementById('statHealth').textContent = s.health_pct + '%';
    const mcpEl = document.getElementById('mcpStatus');
    const a2aEl = document.getElementById('a2aStatus');
    mcpEl.textContent = s.mcp_online ? '● Online' : '○ Offline';
    mcpEl.className = s.mcp_online ? 'font-semibold text-green-400' : 'font-semibold text-red-400';
    a2aEl.textContent = s.a2a_online ? '● Online' : '○ Offline';
    a2aEl.className = s.a2a_online ? 'font-semibold text-green-400' : 'font-semibold text-red-400';
  } catch(e) { console.error('stats', e); }
}

async function loadAgents() {
  try { allAgents = await api('/api/agents'); } catch(e) { allAgents = []; }
  if (currentTab === 'agents') renderCards(filterItems(allAgents));
  populateTeamFilter();
}

async function loadTools() {
  try { allTools = await api('/api/tools'); } catch(e) { allTools = []; }
  if (currentTab === 'tools') renderCards(filterItems(allTools));
  populateTeamFilter();
}

// ============================================================
// TABS & FILTERS
// ============================================================
function switchTab(tab) {
  currentTab = tab;
  document.getElementById('tabAgents').className = tab === 'agents'
    ? 'tab-btn w-full text-left px-3 py-2 rounded-lg text-sm font-medium mb-1 bg-indigo-50 text-indigo-700'
    : 'tab-btn w-full text-left px-3 py-2 rounded-lg text-sm font-medium mb-1 text-gray-600 hover:bg-gray-50';
  document.getElementById('tabTools').className = tab === 'tools'
    ? 'tab-btn w-full text-left px-3 py-2 rounded-lg text-sm font-medium bg-indigo-50 text-indigo-700'
    : 'tab-btn w-full text-left px-3 py-2 rounded-lg text-sm font-medium text-gray-600 hover:bg-gray-50';
  renderCards(filterItems(tab === 'agents' ? allAgents : allTools));
}

function applyFilters() {
  renderCards(filterItems(currentTab === 'agents' ? allAgents : allTools));
}

function filterItems(items) {
  const team = document.getElementById('filterTeam').value;
  const comp = document.getElementById('filterCompliance').value;
  const status = document.getElementById('filterStatus').value;
  return items.filter(i => {
    if (team && i.owner_team !== team) return false;
    if (comp && !i.compliance.includes(comp)) return false;
    if (status && i.status !== status) return false;
    return true;
  });
}

function populateTeamFilter() {
  const sel = document.getElementById('filterTeam');
  const current = sel.value;
  const teams = [...new Set([...allAgents, ...allTools].map(i => i.owner_team).filter(t => t && t !== 'Unassigned'))].sort();
  sel.innerHTML = '<option value="">All Teams</option>' + teams.map(t => `<option ${t===current?'selected':''}>${t}</option>`).join('');
}

// ============================================================
// SEARCH
// ============================================================
function handleSearch(q) {
  clearTimeout(searchTimeout);
  if (!q.trim()) { applyFilters(); return; }
  searchTimeout = setTimeout(async () => {
    try {
      const results = await api(`/api/search?q=${encodeURIComponent(q)}`);
      const tabType = currentTab === 'agents' ? 'agent' : 'tool';
      renderCards(results.filter(r => r.item_type === tabType));
    } catch(e) { console.error(e); }
  }, 300);
}

// ============================================================
// CARD RENDERING
// ============================================================
const itemCache = {};  // id -> item object, populated on each render

function renderCards(items) {
  const grid = document.getElementById('cardGrid');
  const empty = document.getElementById('emptyState');
  if (!items.length) {
    grid.innerHTML = '';
    empty.classList.remove('hidden');
    return;
  }
  empty.classList.add('hidden');
  items.forEach(item => { itemCache[item.id] = item; });
  grid.innerHTML = items.map(item => cardHTML(item)).join('');
}

function cardHTML(item) {
  const isAgent = item.item_type === 'agent';
  const isBlocked = ['pending_review','under_review','rejected'].includes(item.status);
  const statusColor = { active: 'dot-active', approved: 'dot-active', deprecated: 'dot-deprecated', 'under-review': 'dot-review', 'under_review': 'dot-review', 'pending_review': 'dot-review', rejected: 'dot-deprecated' }[item.status] || 'dot-active';
  const unverified = new Set((item.ai_review || {}).unverified_claims || []);
  const badges = (item.compliance || []).map(c => {
    if (unverified.has(c)) return `<span class="text-xs px-1.5 py-0.5 rounded font-medium bg-red-50 text-red-600 line-through" title="Unverified claim">⚠ ${c}</span>`;
    return `<span class="text-xs px-1.5 py-0.5 rounded font-medium ${badgeClass(c)}">${c}</span>`;
  }).join('');
  const authBadge = item.auth_required
    ? `<span class="text-xs px-1.5 py-0.5 rounded font-medium bg-orange-50 text-orange-700">🔐 Auth</span>`
    : '';
  const caps = isAgent && item.capabilities?.length
    ? `<div class="mt-2 flex flex-wrap gap-1">${item.capabilities.slice(0,3).map(c=>`<span class="text-xs bg-indigo-50 text-indigo-700 px-1.5 py-0.5 rounded">${c.replace(/_/g,' ')}</span>`).join('')}${item.capabilities.length>3?`<span class="text-xs text-gray-400">+${item.capabilities.length-3} more</span>`:''}</div>`
    : '';

  return `
  <div onclick="openDetail('${item.id}')"
    class="bg-white rounded-xl shadow-sm border border-gray-100 p-4 cursor-pointer hover:shadow-md hover:border-indigo-200 transition ${isAgent?'card-agent':'card-tool'}">
    <div class="flex items-start justify-between mb-2">
      <div class="flex items-center gap-2">
        <span class="text-lg">${isAgent ? '🤖' : '🔧'}</span>
        <div>
          <h3 class="font-semibold text-gray-800 text-sm leading-tight">${item.name}</h3>
          <p class="text-xs text-gray-400">${item.owner_team}</p>
        </div>
      </div>
      <span class="flex items-center gap-1 text-xs text-gray-500">
        <span class="inline-block w-2 h-2 rounded-full ${statusColor}"></span>
        ${item.status || 'active'}
      </span>
    </div>
    <p class="text-xs text-gray-500 line-clamp-2 mb-2">${item.description || 'No description provided.'}</p>
    ${caps}
    <div class="mt-3 flex flex-wrap gap-1">${badges}${authBadge}${isBlocked ? '<span class="text-xs px-1.5 py-0.5 rounded font-medium badge-blocked">🚫 Blocked</span>' : '<span class="text-xs px-1.5 py-0.5 rounded font-medium badge-approved">✓ Allowed</span>'}</div>
  </div>`;
}

function badgeClass(c) {
  if (c === 'PCI-Scoped') return 'badge-pci';
  if (c === 'PII-Safe')   return 'badge-pii';
  if (c === 'Production-Ready') return 'badge-prod';
  if (c === 'Sandbox-Only') return 'badge-sandbox';
  return 'badge-internal';
}

// ============================================================
// AI GOVERNANCE REVIEW RENDERER
// ============================================================
function aiReviewHTML(review) {
  if (!review) return '';
  const hasRisks      = review.risk_flags && review.risk_flags.length > 0;
  const hasUnverified = review.unverified_claims && review.unverified_claims.length > 0;
  const needsHuman    = review.requires_human_review;

  const headerBg   = (needsHuman || hasRisks) ? 'bg-red-50 border-red-200'
                   : hasUnverified             ? 'bg-amber-50 border-amber-200'
                   :                            'bg-green-50 border-green-200';
  const statusIcon = (needsHuman || hasRisks) ? '🔴' : hasUnverified ? '🟡' : '🟢';
  const statusLabel= (needsHuman || hasRisks) ? 'Issues Found'
                   : hasUnverified             ? 'Claims Unverified'
                   :                            'Passed';

  const scopeChip = (label, val) => {
    const cls = val === 'confirmed' ? 'bg-red-100 text-red-700'
              : val === 'possible'  ? 'bg-amber-100 text-amber-700'
              :                      'bg-gray-100 text-gray-500';
    return `<span class="text-xs px-2 py-0.5 rounded-full font-medium ${cls}">${label}: ${val}</span>`;
  };
  const dupChip = (val) => {
    const cls = val === 'high'   ? 'bg-red-100 text-red-700'
              : val === 'medium' ? 'bg-amber-100 text-amber-700'
              :                    'bg-gray-100 text-gray-500';
    return `<span class="text-xs px-2 py-0.5 rounded-full font-medium ${cls}">Dup risk: ${val}</span>`;
  };

  const riskHTML = hasRisks ? `
    <div class="mt-2">
      <p class="text-xs font-semibold text-red-700 mb-1">⚠️ Risk Flags</p>
      <ul class="space-y-0.5">${review.risk_flags.map(f =>
        `<li class="text-xs text-red-600 flex gap-1.5"><span class="shrink-0">•</span><span>${f}</span></li>`).join('')}
      </ul>
    </div>` : '';

  const unverifiedHTML = hasUnverified ? `
    <div class="mt-2">
      <p class="text-xs font-semibold text-amber-700 mb-1">📋 Unverified Claims</p>
      <ul class="space-y-0.5">${review.unverified_claims.map(u =>
        `<li class="text-xs text-amber-600 flex gap-1.5"><span class="shrink-0">•</span><span>${u}</span></li>`).join('')}
      </ul>
    </div>` : '';

  const unverifiedSet = new Set(review.unverified_claims || []);
  const verifiedCompliance = (review.detected_compliance || []).filter(d => !unverifiedSet.has(d));
  const detectedHTML = verifiedCompliance.length ? `
    <div class="mt-2">
      <p class="text-xs font-semibold text-green-700 mb-1">✅ AI-Verified Compliance</p>
      <div class="flex flex-wrap gap-1">${verifiedCompliance.map(d =>
        `<span class="text-xs px-1.5 py-0.5 bg-green-50 text-green-700 rounded border border-green-200">${d}</span>`).join('')}
      </div>
    </div>` : '';

  const recsHTML = (review.recommendations && review.recommendations.length) ? `
    <div class="mt-2">
      <p class="text-xs font-semibold text-indigo-700 mb-1">💡 Recommendations</p>
      <ul class="space-y-0.5">${review.recommendations.map(r =>
        `<li class="text-xs text-indigo-600 flex gap-1.5"><span class="shrink-0">•</span><span>${r}</span></li>`).join('')}
      </ul>
    </div>` : '';

  const humanBanner = needsHuman ? `
    <div class="mt-2 bg-red-100 border border-red-200 rounded-lg px-3 py-2 text-xs text-red-800 font-semibold">
      🚨 Requires compliance officer review before going live
    </div>` : '';

  return `
  <div class="mt-4 border-t border-gray-100 pt-4">
    <dt class="text-xs font-semibold text-gray-500 uppercase mb-2">🤖 AI Governance Review</dt>
    <dd>
      <div class="border rounded-xl p-3 ${headerBg}">
        <div class="flex items-center gap-2 mb-1">
          <span class="text-sm">${statusIcon}</span>
          <span class="text-xs font-semibold text-gray-800">${statusLabel}</span>
          <span class="ml-auto text-xs text-gray-400">confidence: ${review.confidence || '—'}</span>
        </div>
        <p class="text-xs text-gray-700 leading-relaxed">${review.summary}</p>
        <div class="flex flex-wrap gap-1.5 mt-2">
          ${scopeChip('PCI', review.pci_scope || 'unknown')}
          ${scopeChip('PII', review.pii_scope || 'unknown')}
          ${dupChip(review.duplicate_risk || 'unknown')}
        </div>
        ${riskHTML}
        ${unverifiedHTML}
        ${detectedHTML}
        ${review.auth_assessment ? `
        <div class="mt-2">
          <p class="text-xs font-semibold text-gray-600 mb-0.5">Auth Assessment</p>
          <p class="text-xs text-gray-600">${review.auth_assessment}</p>
        </div>` : ''}
        ${recsHTML}
        ${humanBanner}
      </div>

      ${review.ai_governance ? aiGovernanceSectionHTML(review.ai_governance) : ''}
    </dd>
  </div>`;
}

function aiGovernanceSectionHTML(gov) {
  if (!gov) return '';

  const classChip = (label, val, goodVals, badVals) => {
    const cls = badVals.includes(val) ? 'bg-red-100 text-red-700'
              : goodVals.includes(val) ? 'bg-green-100 text-green-700'
              : 'bg-amber-100 text-amber-700';
    return `<span class="text-xs px-2 py-0.5 rounded-full font-medium ${cls}">${label}: ${val}</span>`;
  };

  const issueList = (items) => {
    if (!items || !items.length) return '';
    return `<ul class="mt-1 space-y-0.5">${items.map(i =>
      `<li class="text-xs text-red-600 flex gap-1.5"><span class="shrink-0">•</span><span>${i}</span></li>`).join('')}</ul>`;
  };

  const boolIcon = (val) => val ? '✅' : '❌';

  const sections = [];

  // 16. Human-in-the-Loop
  if (gov.human_in_the_loop) {
    const h = gov.human_in_the_loop;
    sections.push(`<div class="mb-2">
      <div class="flex items-center gap-2 mb-1">
        <span class="text-xs font-semibold text-gray-700">👤 Human-in-the-Loop</span>
        ${classChip('', h.classification, ['required_and_present','not_required'], ['required_but_missing'])}
      </div>
      ${h.autonomous_actions?.length ? `<p class="text-xs text-gray-500">Autonomous actions: ${h.autonomous_actions.join(', ')}</p>` : ''}
      <p class="text-xs text-gray-500">${boolIcon(h.has_escalation_path)} Escalation path &nbsp; ${boolIcon(h.has_confidence_threshold)} Confidence threshold</p>
      ${issueList(h.issues)}
    </div>`);
  }

  // 17. Model Transparency
  if (gov.model_transparency) {
    const m = gov.model_transparency;
    sections.push(`<div class="mb-2">
      <div class="flex items-center gap-2 mb-1">
        <span class="text-xs font-semibold text-gray-700">📋 Model Transparency</span>
        ${classChip('', m.classification, ['comprehensive'], ['missing'])}
      </div>
      <p class="text-xs text-gray-500">${boolIcon(m.model_declared)} Model declared &nbsp; ${boolIcon(m.limitations_documented)} Limitations documented &nbsp; ${boolIcon(m.intended_use_stated)} Intended use stated</p>
      ${issueList(m.issues)}
    </div>`);
  }

  // 18. Guardrails
  if (gov.guardrails) {
    const g = gov.guardrails;
    sections.push(`<div class="mb-2">
      <div class="flex items-center gap-2 mb-1">
        <span class="text-xs font-semibold text-gray-700">🛡️ Guardrails & Content Filtering</span>
        ${classChip('', g.classification, ['implemented'], ['none'])}
      </div>
      <p class="text-xs text-gray-500">${boolIcon(g.has_output_filtering)} Output filtering &nbsp; ${boolIcon(g.has_topic_restrictions)} Topic restrictions &nbsp; ${boolIcon(g.has_safety_layer)} Safety layer</p>
      ${issueList(g.issues)}
    </div>`);
  }

  // 19. Bias & Fairness
  if (gov.bias_fairness) {
    const b = gov.bias_fairness;
    sections.push(`<div class="mb-2">
      <div class="flex items-center gap-2 mb-1">
        <span class="text-xs font-semibold text-gray-700">⚖️ Bias & Fairness</span>
        ${classChip('', b.classification, ['assessed','not_applicable'], ['at_risk'])}
      </div>
      <p class="text-xs text-gray-500">${boolIcon(b.has_fairness_testing)} Fairness testing &nbsp; ${b.uses_proxy_variables ? '⚠️ Uses proxy variables' : '✅ No proxy variables'}</p>
      ${issueList(b.issues)}
    </div>`);
  }

  // 20. Explainability
  if (gov.explainability) {
    const e = gov.explainability;
    sections.push(`<div class="mb-2">
      <div class="flex items-center gap-2 mb-1">
        <span class="text-xs font-semibold text-gray-700">🔍 Explainability & Auditability</span>
        ${classChip('', e.classification, ['comprehensive'], ['none'])}
      </div>
      <p class="text-xs text-gray-500">${boolIcon(e.has_decision_logging)} Decision logging &nbsp; ${boolIcon(e.has_reasoning_traces)} Reasoning traces &nbsp; ${boolIcon(e.has_user_explanations)} User explanations</p>
      ${issueList(e.issues)}
    </div>`);
  }

  // 21. Grounding
  if (gov.grounding) {
    const g = gov.grounding;
    sections.push(`<div class="mb-2">
      <div class="flex items-center gap-2 mb-1">
        <span class="text-xs font-semibold text-gray-700">📌 Grounding & RAG</span>
        ${classChip('', g.classification, ['grounded','not_applicable'], ['ungrounded'])}
      </div>
      <p class="text-xs text-gray-500">${boolIcon(g.uses_rag)} Uses RAG &nbsp; ${boolIcon(g.has_source_attribution)} Source attribution &nbsp; ${boolIcon(g.has_source_validation)} Source validation</p>
      ${issueList(g.issues)}
    </div>`);
  }

  // 22. Model Fallback
  if (gov.model_fallback) {
    const f = gov.model_fallback;
    sections.push(`<div class="mb-2">
      <div class="flex items-center gap-2 mb-1">
        <span class="text-xs font-semibold text-gray-700">🔄 Model Fallback & Degradation</span>
        ${classChip('', f.classification, ['resilient'], ['fragile'])}
      </div>
      <p class="text-xs text-gray-500">Failure mode: ${f.failure_mode || 'unknown'} &nbsp; ${boolIcon(f.has_fallback_logic)} Fallback logic &nbsp; ${boolIcon(f.has_circuit_breaker)} Circuit breaker</p>
      ${issueList(f.issues)}
    </div>`);
  }

  // 23. Data Sent to Provider
  if (gov.data_sent_to_provider) {
    const d = gov.data_sent_to_provider;
    sections.push(`<div class="mb-2">
      <div class="flex items-center gap-2 mb-1">
        <span class="text-xs font-semibold text-gray-700">📤 Data Sent to Model Provider</span>
        ${classChip('', d.classification, ['safe'], ['confirmed_exposure'])}
      </div>
      <p class="text-xs text-gray-500">${d.pii_in_prompts ? '🔴 PII in prompts' : '✅ No PII in prompts'} &nbsp; ${d.pci_in_prompts ? '🔴 PCI in prompts' : '✅ No PCI in prompts'} &nbsp; ${boolIcon(d.data_minimization)} Data minimization</p>
      ${issueList(d.issues)}
    </div>`);
  }

  // 24. Consent & Disclosure
  if (gov.consent_disclosure) {
    const c = gov.consent_disclosure;
    sections.push(`<div class="mb-2">
      <div class="flex items-center gap-2 mb-1">
        <span class="text-xs font-semibold text-gray-700">📜 Consent & AI Disclosure</span>
        ${classChip('', c.classification, ['compliant','not_applicable'], ['missing'])}
      </div>
      <p class="text-xs text-gray-500">${boolIcon(c.has_ai_disclosure)} AI disclosure &nbsp; ${boolIcon(c.has_consent_mechanism)} Consent mechanism &nbsp; ${boolIcon(c.has_opt_out)} Opt-out</p>
      ${issueList(c.issues)}
    </div>`);
  }

  // 25. Model Version Pinning
  if (gov.model_version_pinning) {
    const v = gov.model_version_pinning;
    sections.push(`<div class="mb-2">
      <div class="flex items-center gap-2 mb-1">
        <span class="text-xs font-semibold text-gray-700">📌 Model Version Pinning</span>
        ${classChip('', v.classification, ['pinned'], ['floating'])}
      </div>
      <p class="text-xs text-gray-500">Version: ${v.detected_version || 'unknown'} &nbsp; ${boolIcon(v.version_in_config)} In config &nbsp; ${boolIcon(v.has_regression_tests)} Regression tests</p>
      ${issueList(v.issues)}
    </div>`);
  }

  if (!sections.length) return '';

  return `
    <div class="mt-3 border-t border-gray-200 pt-3">
      <p class="text-xs font-semibold text-purple-700 mb-2">🏛️ AI Governance Assessment</p>
      <div class="space-y-1">
        ${sections.join('')}
      </div>
    </div>`;
}

// ============================================================
// DETAIL PANEL
// ============================================================
async function openDetail(itemId) {
  const item = itemCache[itemId];
  if (!item) return;
  const isAgent = item.item_type === 'agent';
  const isBlocked = ['pending_review','under_review','rejected'].includes(item.status);
  const enforcementBadge = isBlocked
    ? `<div class="mt-2 bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-xs text-red-800 font-semibold">
        🚫 BLOCKED — This ${isAgent ? 'agent' : 'tool'} cannot be invoked. Status: ${item.status}.
        ${item.status === 'rejected' ? 'It was rejected by an admin.' : 'Admin approval required.'}
      </div>`
    : `<div class="mt-2 bg-green-50 border border-green-200 rounded-lg px-3 py-2 text-xs text-green-800 font-semibold">
        ✓ APPROVED — This ${isAgent ? 'agent' : 'tool'} is allowed to receive traffic.
      </div>`;
  const detailUnverified = new Set((item.ai_review || {}).unverified_claims || []);
  const badges = (item.compliance || []).map(c => {
    if (detailUnverified.has(c)) return `<span class="text-xs px-2 py-1 rounded font-medium bg-red-50 text-red-600 line-through" title="Unverified claim">⚠ ${c}</span>`;
    return `<span class="text-xs px-2 py-1 rounded font-medium ${badgeClass(c)}">${c}</span>`;
  }).join('');
  const caps = isAgent && item.capabilities?.length
    ? `<div class="mt-1 flex flex-wrap gap-1">${item.capabilities.map(c=>`<span class="text-xs bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded">${c.replace(/_/g,' ')}</span>`).join('')}</div>`
    : '<p class="text-sm text-gray-400 mt-1">None specified</p>';

  // Fetch tools linked to this agent (if it's an agent)
  let toolsHTML = '';
  let agentTools = [];
  if (isAgent) {
    try {
      agentTools = await api(`/api/agent/${item.id}/tools`);
      agentToolsCache[item.id] = agentTools;
      if (agentTools.length) {
        toolsHTML = `
          <div>
            <dt class="text-xs font-semibold text-gray-500 uppercase mb-2">Registered Tools (${agentTools.length})</dt>
            <dd class="space-y-2">
              ${agentTools.map(t => `
                <div class="bg-gray-50 rounded-lg p-2.5 border border-gray-100">
                  <div class="flex items-center justify-between mb-1">
                    <span class="text-sm font-medium text-gray-800">🔧 ${t.name}</span>
                    <span class="text-xs text-gray-400">POST only</span>
                  </div>
                  <p class="text-xs text-gray-500">${t.description || ''}</p>
                  ${t.endpoint ? `<p class="text-xs text-gray-400 mt-1 font-mono truncate">${t.endpoint}</p>` : ''}
                </div>`).join('')}
            </dd>
          </div>`;
      }
    } catch(e) { /* ignore */ }
  }

  // Source agent link for tools
  const sourceAgentHTML = (!isAgent && item.source_agent)
    ? `<div><dt class="text-xs font-semibold text-gray-500 uppercase">Part of Agent</dt>
        <dd class="mt-1 text-indigo-600 text-sm">🤖 ${item.source_agent.replace(/_/g,' ')}</dd></div>`
    : '';

  document.getElementById('detailContent').innerHTML = `
    <div class="mb-5">
      <div class="flex items-center gap-2 mb-1">
        <span class="text-2xl">${isAgent ? '🤖' : '🔧'}</span>
        <div>
          <h2 class="text-lg font-bold text-gray-800">${item.name}</h2>
          <span class="text-xs font-medium px-2 py-0.5 rounded ${isAgent?'bg-indigo-100 text-indigo-700':'bg-sky-100 text-sky-700'}">${isAgent ? 'Agent' : 'Tool'}</span>
        </div>
      </div>
      ${enforcementBadge}
      ${item.status === 'under_review' ? `
      <div class="mt-3 flex gap-2">
        <button onclick="approveAgent('${item.id}')" class="flex-1 bg-green-600 text-white text-xs font-semibold py-2 rounded-lg hover:bg-green-700 transition">
          ✓ Approve
        </button>
        <button onclick="rejectAgent('${item.id}')" class="flex-1 bg-red-600 text-white text-xs font-semibold py-2 rounded-lg hover:bg-red-700 transition">
          ✗ Reject
        </button>
      </div>` : ''}
      ${item.status === 'pending_review' && item.ai_review ? `
      <div class="mt-3">
        <button onclick="approveAgent('${item.id}')" class="w-full bg-green-600 text-white text-xs font-semibold py-2 rounded-lg hover:bg-green-700 transition">
          ✓ Approve (Review Complete)
        </button>
      </div>` : ''}
      ${item.status === 'pending_review' && !item.ai_review ? `
      <div class="mt-3 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-xs text-amber-800">
        ⏳ AI governance review in progress... Check back in a few moments.
      </div>` : ''}
    </div>
    <dl class="space-y-4 text-sm">
      <div><dt class="text-xs font-semibold text-gray-500 uppercase">Description</dt>
        <dd class="mt-1 text-gray-700">${item.description || 'No description provided.'}</dd></div>
      <div><dt class="text-xs font-semibold text-gray-500 uppercase">Owner Team</dt>
        <dd class="mt-1 font-medium text-gray-800">${item.owner_team}</dd></div>
      ${isAgent ? `<div><dt class="text-xs font-semibold text-gray-500 uppercase">Agent Type</dt>
        <dd class="mt-1 text-gray-700">${item.agent_type || '-'}</dd></div>
        <div><dt class="text-xs font-semibold text-gray-500 uppercase">Capabilities</dt>${caps}</div>
        ${item.did ? `<div><dt class="text-xs font-semibold text-gray-500 uppercase">DID (Decentralized Identifier)</dt>
        <dd class="mt-1 flex items-center gap-2">
          <code class="text-xs bg-indigo-50 text-indigo-700 px-2 py-1 rounded font-mono break-all">${item.did}</code>
          <button onclick="navigator.clipboard.writeText('${item.did}').then(()=>this.textContent='✓').catch(()=>{})"
            class="shrink-0 text-xs text-gray-400 hover:text-indigo-600 border border-gray-200 rounded px-1.5 py-0.5">copy</button>
        </dd></div>` : ''}
        <div><dt class="text-xs font-semibold text-gray-500 uppercase">Receive Endpoint</dt>
        <dd class="mt-1 text-gray-500 text-xs break-all">${item.endpoint || '-'}</dd></div>` : ''}
      ${sourceAgentHTML}
      ${toolsHTML}
      <div><dt class="text-xs font-semibold text-gray-500 uppercase">Compliance</dt>
        <dd class="mt-1 flex flex-wrap gap-1">${badges || '<span class="text-gray-400">None</span>'}</dd></div>
      ${!isAgent && item.auth_required ? `
      <div><dt class="text-xs font-semibold text-gray-500 uppercase">Authentication</dt>
        <dd class="mt-1">
          <span class="inline-flex items-center gap-1.5 text-xs font-medium bg-orange-50 text-orange-700 border border-orange-200 px-2 py-1 rounded-lg">
            🔐 Required${item.auth_type ? ` — ${item.auth_type}` : ''}
          </span>
          <p class="text-xs text-gray-400 mt-1">Include the appropriate header in every request to this tool.</p>
        </dd></div>` : ''}
      ${!isAgent && item.sandbox_endpoint ? `
      <div><dt class="text-xs font-semibold text-gray-500 uppercase">Sandbox Endpoint</dt>
        <dd class="mt-1 flex items-center gap-2">
          <code class="text-xs text-green-700 bg-green-50 px-2 py-0.5 rounded font-mono break-all">${item.sandbox_endpoint}</code>
          <span class="shrink-0 text-xs text-green-600 border border-green-200 rounded px-1.5 py-0.5">safe to test</span>
        </dd></div>` : ''}
      <div><dt class="text-xs font-semibold text-gray-500 uppercase">Status</dt>
        <dd class="mt-1">${item.status || 'active'}</dd></div>
      <div><dt class="text-xs font-semibold text-gray-500 uppercase">Registered</dt>
        <dd class="mt-1 text-gray-700">${item.registered_at || '-'}</dd></div>
      ${item.docs_url ? `<div><dt class="text-xs font-semibold text-gray-500 uppercase">Documentation</dt>
        <dd class="mt-1"><a href="${item.docs_url}" class="text-indigo-600 hover:underline text-xs break-all">${item.docs_url}</a></dd></div>` : ''}
      ${item.source_repo ? `<div><dt class="text-xs font-semibold text-gray-500 uppercase">Source Code</dt>
        <dd class="mt-1 flex items-center gap-2">
          <svg class="w-4 h-4 text-gray-500" fill="currentColor" viewBox="0 0 24 24"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/></svg>
          <a href="${item.source_repo}" class="text-indigo-600 hover:underline text-xs break-all">${item.source_repo}</a>
        </dd></div>` : ''}
      ${item.ai_review ? aiReviewHTML(item.ai_review) : ''}
    </dl>
    ${buildHowToUse(item, agentTools)}`;

  document.getElementById('detailOverlay').classList.remove('hidden');
  document.getElementById('detailPanel').classList.remove('translate-x-full');
}

function buildHowToUse(item, agentTools = []) {
  const isAgent = item.item_type === 'agent';
  const caps = item.capabilities || [];
  const firstCap = caps[0] || 'your_capability';
  // Use the real DID from the A2A registry if available
  const agentDid = item.did || (item.id ? 'did:key:z6Mk' + item.id.replace(/_/g,'') : 'did:key:...');

  if (isAgent) {
    // Build Try It panel if tools with example payloads exist
    const toolsWithExamples = agentTools.filter(t => t.example_request && Object.keys(t.example_request).length);
    const agentPayload = toolsWithExamples.length
      ? JSON.stringify(toolsWithExamples[0].example_request, null, 2)
      : '{}';

    const fullAgentSnippet =
`#!/usr/bin/env python3
# Invoke ${item.name} -- ${item.owner_team}
# Discovers the agent from the A2A registry, then sends an A2A message.
# Replace PAYLOAD with your data and update the placeholder DID fields.
#
# Run:  pip install httpx
#       python this_script.py

import httpx
import json

A2A_SERVER = "http://localhost:9000"
AGENT_ID   = "${item.id}"
CAPABILITY = "${firstCap}"   # message_type sent to the agent

# -- Replace with your actual payload ----------------------------------
PAYLOAD = ${agentPayload}
# ----------------------------------------------------------------------

def main():
    # 1. Discover the agent DID from the A2A registry
    resp   = httpx.get(f"{A2A_SERVER}/agents")
    agents = resp.json()["agents"]
    agent  = next(a for a in agents if a["agent_id"] == AGENT_ID)
    to_did = agent["did"]
    print(f"  Agent DID: {to_did}")

    # 2. Send the A2A message
    r = httpx.post(f"{A2A_SERVER}/messages/send", json={
        "from_did":     "did:key:YOUR_DID_HERE",
        "to_did":       to_did,
        "message_type": CAPABILITY,
        "body":         PAYLOAD,
        "signature":    "YOUR_SIGNATURE_HERE"
    })
    r.raise_for_status()
    print(json.dumps(r.json(), indent=2))

if __name__ == "__main__":
    main()`;

    const tryItPanel = toolsWithExamples.length ? `
    <div class="mt-4 border-t border-gray-100 pt-3">
      <button onclick="toggleAgentTry()" class="text-xs font-semibold text-emerald-600 hover:text-emerald-800 flex items-center gap-1">
        ▶ Try It Live — Send Real A2A Message
      </button>
      <div id="agentTryBox" class="hidden mt-2">
        <div class="p-2 bg-emerald-50 border border-emerald-100 rounded-lg text-xs text-emerald-800 mb-2">
          Sends a real A2A-format message to this agent's <code>/receive</code> endpoint and shows the live response.
        </div>
        <label class="text-xs font-semibold text-gray-600 block mb-1">Capability (message_type)</label>
        <select id="agentCapSelector" onchange="updateAgentTryPayload('${item.id}')"
          class="w-full text-xs border border-gray-200 rounded-lg px-2 py-1.5 mb-2">
          ${toolsWithExamples.map(t => `<option value="${t.id}">${t.name}</option>`).join('')}
        </select>
        <label class="text-xs font-semibold text-gray-600 block mb-1">body payload (JSON)</label>
        <textarea id="agentTryPayload" rows="5"
          class="w-full text-xs font-mono border border-gray-200 rounded-lg p-2 focus:outline-none focus:ring-1 focus:ring-emerald-300"
        >${JSON.stringify(toolsWithExamples[0]?.example_request || {}, null, 2)}</textarea>
        <button onclick="runAgentTry('${item.id}')"
          class="mt-2 w-full bg-emerald-600 text-white text-xs font-semibold py-1.5 rounded-lg hover:bg-emerald-700 transition">
          Send A2A Message →
        </button>
        <div id="agentTryResult" class="hidden mt-2 bg-gray-900 text-green-400 text-xs font-mono rounded-lg p-3 max-h-48 overflow-y-auto whitespace-pre"></div>
      </div>
    </div>` : '';

    return `
  <div class="mt-5 border-t border-gray-100 pt-4">
    <p class="text-xs font-semibold text-gray-500 uppercase mb-3">How to Use This Agent</p>
    <div class="mb-3 p-3 bg-blue-50 border border-blue-100 rounded-lg text-xs text-blue-800">
      <strong>Key concept:</strong> Agents are invoked via <strong>message passing</strong>, not direct HTTP.
      Discover the DID from the A2A registry, then send a typed message — routing is handled by the bus.
    </div>
    <p class="text-xs font-semibold text-gray-600 mb-1">Complete Python script — copy, fill in your DID, run</p>
    <div class="relative bg-gray-900 rounded-lg p-3 overflow-x-auto">
      <button onclick="navigator.clipboard.writeText(this.nextElementSibling.textContent).then(()=>{this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',1500)})"
        class="absolute top-2 right-2 text-xs text-gray-400 hover:text-white bg-gray-700 hover:bg-gray-600 px-2 py-0.5 rounded transition">Copy</button>
      <pre class="text-xs text-green-400 font-mono whitespace-pre">${fullAgentSnippet}</pre>
    </div>
    ${tryItPanel}
  </div>`;
  }

  // Tool: direct HTTP call
  // Try It always uses sandbox_endpoint when available — never accidentally hit prod
  const tryItEndpoint = item.sandbox_endpoint || item.endpoint;

  const exJson = JSON.stringify(
    item.example_request && Object.keys(item.example_request).length
      ? item.example_request : {}, null, 2);

  // Auth header constant for the Python snippet
  const authHeader = item.auth_required
    ? (item.auth_type === 'api_key'
        ? 'HEADERS  = {"X-API-Key": "demo-key-12345"}  # required -- replace with your key'
        : 'HEADERS  = {"Authorization": "Bearer YOUR_TOKEN_HERE"}  # required')
    : 'HEADERS  = {}  # no auth required';

  const pythonSnippet =
`#!/usr/bin/env python3
# ${item.name} -- ${item.owner_team}
# Endpoint : ${item.endpoint}
# Auth     : ${item.auth_required ? item.auth_type : 'none required'}
#
# Run:  pip install httpx
#       python this_script.py

import httpx
import json

ENDPOINT = "${item.endpoint}"
${authHeader}
PAYLOAD  = ${exJson}

def main():
    r = httpx.post(ENDPOINT, json=PAYLOAD, headers=HEADERS)
    r.raise_for_status()
    print(json.dumps(r.json(), indent=2))

if __name__ == "__main__":
    main()`;

  const tryItSection = tryItEndpoint ? `
    <div class="mt-3 border-t border-gray-100 pt-3">
      <button onclick="toggleTryIt()" class="text-xs font-semibold text-indigo-600 hover:text-indigo-800 flex items-center gap-1">
        ▶ Try It Live
      </button>
      <div id="tryItBox" class="hidden mt-2">
        ${item.sandbox_endpoint
          ? `<p class="text-xs text-green-700 bg-green-50 border border-green-100 rounded px-2 py-1 mb-2">
              Using sandbox endpoint — safe to call freely.</p>`
          : (item.auth_required
              ? `<p class="text-xs text-orange-700 bg-orange-50 border border-orange-100 rounded px-2 py-1 mb-2">
                  🔐 This tool requires authentication. Add the required header below before running.</p>`
              : '')}
        <label class="text-xs font-semibold text-gray-600 block mb-1">Request body (JSON)</label>
        <textarea id="tryItPayload" rows="5"
          class="w-full text-xs font-mono border border-gray-200 rounded-lg p-2 focus:outline-none focus:ring-1 focus:ring-indigo-300"
          >${exJson}</textarea>
        <!-- Headers panel -->
        <div class="mt-2">
          <button onclick="toggleHeaders()" class="text-xs text-gray-500 hover:text-indigo-600 flex items-center gap-1">
            <span id="headersToggleIcon">▶</span> Request Headers ${item.auth_required ? '<span class="text-orange-600 font-semibold">(auth required)</span>' : '(optional)'}
          </button>
          <div id="headersBox" class="${item.auth_required ? '' : 'hidden'} mt-2">
            <div id="headersList" class="space-y-1">
              ${item.auth_required ? `
              <div class="flex gap-1 items-center header-row">
                <input value="${item.auth_type === 'api_key' ? 'X-API-Key' : 'Authorization'}"
                  class="w-36 text-xs border border-gray-200 rounded px-2 py-1 header-name font-mono" placeholder="Header">
                <input value="${item.auth_type === 'api_key' ? 'demo-key-12345' : ''}"
                  class="flex-1 text-xs border border-gray-200 rounded px-2 py-1 header-value font-mono" placeholder="${item.auth_type === 'api_key' ? 'your-api-key' : 'Bearer your-token'}">
                <button onclick="this.closest('.header-row').remove()" class="text-gray-300 hover:text-red-500 text-xs px-1">✕</button>
              </div>` : ''}
            </div>
            <button onclick="addHeader()" class="text-xs text-indigo-500 hover:underline mt-1">+ Add header</button>
          </div>
        </div>
        <button onclick="runTryIt('${tryItEndpoint}')"
          class="mt-2 w-full bg-indigo-600 text-white text-xs font-semibold py-1.5 rounded-lg hover:bg-indigo-700 transition">
          Run →
        </button>
        <div id="tryItResult" class="hidden mt-2 bg-gray-900 text-green-400 text-xs font-mono rounded-lg p-3 max-h-40 overflow-y-auto whitespace-pre"></div>
      </div>
    </div>` : '';

  // Build parameter table.
  // MCP tools wrap fields as {"parameters": {...}}; other tools use flat {"field": value}.
  // Always show the actual business fields, not the wrapper key.
  const rawEx = item.example_request || {};
  const paramFields = (rawEx.parameters !== undefined)
    ? Object.entries(rawEx.parameters)   // MCP-style: unwrap the "parameters" key
    : Object.entries(rawEx);             // flat style (fraud agent tools, etc.)

  const paramsSection = paramFields.length
    ? `<div class="mt-3">
        <p class="text-xs font-semibold text-gray-600 mb-1">Input Parameters</p>
        <table class="w-full text-xs border-collapse">
          <thead>
            <tr class="text-left text-gray-400 border-b border-gray-100">
              <th class="pb-1 pr-3 font-medium">Field</th>
              <th class="pb-1 pr-3 font-medium">Type</th>
              <th class="pb-1 font-medium">Example value</th>
            </tr>
          </thead>
          <tbody>
            ${paramFields.map(([k, v]) => `
            <tr class="border-b border-gray-50">
              <td class="py-1 pr-3 font-mono text-indigo-700">${k}</td>
              <td class="py-1 pr-3 text-gray-500">${typeof v}</td>
              <td class="py-1 text-gray-600 font-mono">${JSON.stringify(v)}</td>
            </tr>`).join('')}
          </tbody>
        </table>
      </div>`
    : `<p class="text-xs text-gray-400 mt-2 italic">No input parameters required.</p>`;

  return `
  <div class="mt-5 border-t border-gray-100 pt-4">
    <p class="text-xs font-semibold text-gray-500 uppercase mb-2">How to Use This Tool</p>
    <div class="mb-2 p-3 bg-sky-50 border border-sky-100 rounded-lg text-xs text-sky-800">
      <strong>Key concept:</strong> Tools are <strong>direct HTTP calls</strong> — stateless functions
      with a fixed endpoint. Call them from any language or framework.
    </div>
    ${paramsSection}
    <p class="text-xs font-semibold text-gray-600 mt-3 mb-1">Python — copy, replace values, run</p>
    <div class="relative bg-gray-900 rounded-lg p-3 overflow-x-auto">
      <button onclick="navigator.clipboard.writeText(this.nextElementSibling.textContent).then(()=>{this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',1500)})"
        class="absolute top-2 right-2 text-xs text-gray-400 hover:text-white bg-gray-700 hover:bg-gray-600 px-2 py-0.5 rounded transition">Copy</button>
      <pre class="text-xs text-green-400 font-mono whitespace-pre">${pythonSnippet}</pre>
    </div>
    ${tryItSection}
  </div>`;
}

function toggleTryIt() {
  document.getElementById('tryItBox').classList.toggle('hidden');
}

function toggleHeaders() {
  const box = document.getElementById('headersBox');
  const icon = document.getElementById('headersToggleIcon');
  box.classList.toggle('hidden');
  icon.textContent = box.classList.contains('hidden') ? '▶' : '▼';
}

function addHeader() {
  const row = document.createElement('div');
  row.className = 'flex gap-1 items-center header-row';
  row.innerHTML = `
    <input class="w-36 text-xs border border-gray-200 rounded px-2 py-1 header-name font-mono" placeholder="Header name">
    <input class="flex-1 text-xs border border-gray-200 rounded px-2 py-1 header-value font-mono" placeholder="Value">
    <button onclick="this.closest('.header-row').remove()" class="text-gray-300 hover:text-red-500 text-xs px-1">✕</button>`;
  document.getElementById('headersList').appendChild(row);
}

async function runTryIt(endpoint) {
  const payloadRaw = document.getElementById('tryItPayload').value;
  const resultEl = document.getElementById('tryItResult');
  resultEl.classList.remove('hidden');

  // Check enforcement — find the current item from cache
  const currentItem = Object.values(itemCache).find(i => 
    (i.endpoint === endpoint || i.sandbox_endpoint === endpoint));
  if (currentItem && ['pending_review','under_review','rejected'].includes(currentItem.status)) {
    resultEl.textContent = `\u26d4 BLOCKED by governance.\nStatus: ${currentItem.status}\nThis tool must be approved by an admin before it can be invoked.`;
    resultEl.className = resultEl.className.replace('text-green-400','text-red-400');
    return;
  }

  resultEl.textContent = 'Calling...';

  // Collect any headers the user filled in
  const headers = {};
  document.querySelectorAll('.header-row').forEach(row => {
    const name  = row.querySelector('.header-name')?.value?.trim();
    const value = row.querySelector('.header-value')?.value?.trim();
    if (name && value) headers[name] = value;
  });

  try {
    const payload = JSON.parse(payloadRaw);
    const result = await api('/api/proxy', 'POST', { endpoint, payload, headers });
    resultEl.textContent = JSON.stringify(result.response || result, null, 2);
  } catch(e) {
    resultEl.textContent = 'Error: ' + e.message;
  }
}

// ============================================================
// AGENT TRY IT
// ============================================================
function toggleAgentTry() {
  document.getElementById('agentTryBox').classList.toggle('hidden');
}

function updateAgentTryPayload(agentId) {
  const sel = document.getElementById('agentCapSelector');
  const toolId = sel.value;
  const tools = agentToolsCache[agentId] || [];
  const tool = tools.find(t => t.id === toolId);
  document.getElementById('agentTryPayload').value =
    JSON.stringify(tool?.example_request || {}, null, 2);
}

async function runAgentTry(agentId) {
  const capability = document.getElementById('agentCapSelector').value;
  const payloadRaw = document.getElementById('agentTryPayload').value;
  const resultEl = document.getElementById('agentTryResult');
  resultEl.classList.remove('hidden');

  // Check enforcement
  const agent = itemCache[agentId];
  if (agent && ['pending_review','under_review','rejected'].includes(agent.status)) {
    resultEl.textContent = `\u26d4 BLOCKED by governance.\nStatus: ${agent.status}\nThis agent must be approved by an admin before it can receive messages.`;
    resultEl.className = resultEl.className.replace('text-green-400','text-red-400');
    return;
  }

  resultEl.textContent = 'Sending A2A message...';
  try {
    const payload = JSON.parse(payloadRaw);
    const result = await api('/api/invoke-agent', 'POST', { agent_id: agentId, capability, payload });
    resultEl.textContent = JSON.stringify(result.response || result, null, 2);
  } catch(e) {
    resultEl.textContent = 'Error: ' + e.message;
  }
}

function closeDetail() {
  document.getElementById('detailOverlay').classList.add('hidden');
  document.getElementById('detailPanel').classList.add('translate-x-full');
}

// ============================================================
// REGISTER PANEL
// ============================================================
function renderComplianceTags() {
  const opts = ['PCI-Scoped','PII-Safe','Production-Ready','Sandbox-Only','Internal-Only'];
  document.getElementById('complianceTags').innerHTML = opts.map(o => `
    <label class="flex items-center gap-1.5 text-xs cursor-pointer select-none">
      <input type="checkbox" value="${o}" class="compliance-cb rounded"> ${o}
    </label>`).join('');
}

function toggleRegType() {
  const isAgent = document.querySelector('input[name="regType"]:checked').value === 'agent';
  document.getElementById('agentFields').style.display = isAgent ? '' : 'none';
}

function openRegisterPanel() {
  document.getElementById('registerForm').reset();
  document.getElementById('similarWarn').classList.add('hidden');
  document.getElementById('regError').classList.add('hidden');
  document.getElementById('regSuccess').classList.add('hidden');
  document.getElementById('agentFields').style.display = '';
  document.getElementById('registerOverlay').classList.remove('hidden');
  document.getElementById('registerPanel').classList.remove('translate-x-full');
}

function closeRegister() {
  document.getElementById('registerOverlay').classList.add('hidden');
  document.getElementById('registerPanel').classList.add('translate-x-full');
}

async function checkSimilarity() {
  clearTimeout(similarTimeout);
  const name = document.getElementById('regId').value;
  const desc = document.getElementById('regDescription').value;
  if (!name && !desc) { document.getElementById('similarWarn').classList.add('hidden'); return; }
  similarTimeout = setTimeout(async () => {
    try {
      const matches = await api(`/api/similarity?name=${encodeURIComponent(name)}&description=${encodeURIComponent(desc)}`);
      const warnEl = document.getElementById('similarWarn');
      const listEl = document.getElementById('similarList');
      if (matches.length) {
        listEl.innerHTML = matches.map(m => `
          <div class="text-xs text-amber-700">
            <span class="font-medium">${m.name}</span>
            <span class="text-amber-500 ml-1">(${m.similarity_score}% match)</span>
            — ${m.owner_team}
          </div>`).join('');
        warnEl.classList.remove('hidden');
      } else {
        warnEl.classList.add('hidden');
      }
    } catch(e) { /* ignore */ }
  }, 400);
}

async function submitRegister(e) {
  e.preventDefault();
  const type = document.querySelector('input[name="regType"]:checked').value;
  const id = document.getElementById('regId').value.trim();
  const desc = document.getElementById('regDescription').value.trim();
  const team = document.getElementById('regTeam').value.trim();
  const docs = document.getElementById('regDocs').value.trim();
  const sourceRepo = document.getElementById('regSourceRepo').value.trim();
  const compliance = [...document.querySelectorAll('.compliance-cb:checked')].map(c => c.value);

  const errEl = document.getElementById('regError');
  const okEl  = document.getElementById('regSuccess');
  errEl.classList.add('hidden');
  okEl.classList.add('hidden');

  if (!id || !team) { errEl.textContent = 'Name/ID and Owner Team are required.'; errEl.classList.remove('hidden'); return; }
  if (!sourceRepo || (!sourceRepo.startsWith('http://') && !sourceRepo.startsWith('https://'))) {
    errEl.textContent = 'Source Code Repository is required and must be a valid URL (http:// or https://).';
    errEl.classList.remove('hidden');
    return;
  }

  // Show loading state while AI review runs (may take a few seconds)
  const submitBtn = document.querySelector('#registerForm button[type="submit"]');
  submitBtn.textContent = 'Registering + AI Review…';
  submitBtn.disabled = true;

  try {
    let result;
    if (type === 'agent') {
      const caps = document.getElementById('regCapabilities').value.split(',').map(s=>s.trim()).filter(Boolean);
      result = await api('/api/register/agent', 'POST', {
        agent_id: id,
        agent_type: document.getElementById('regAgentType').value.trim() || 'custom',
        endpoint: document.getElementById('regEndpoint').value.trim() || 'http://localhost:8100/receive',
        capabilities: caps,
        owner_team: team,
        compliance,
        docs_url: docs,
        source_repo: sourceRepo,
        description: desc,
      });
    } else {
      result = await api('/api/register/tool', 'POST', { tool_id: id, description: desc, owner_team: team, compliance, docs_url: docs, source_repo: sourceRepo });
    }

    // Show result — include AI review if present
    if (result.ai_review) {
      okEl.innerHTML = `
        <p class="font-semibold text-green-700 mb-2">✓ ${id} registered successfully.</p>
        ${aiReviewHTML(result.ai_review)}
        <button onclick="closeRegister();loadAll();"
          class="mt-3 w-full text-xs bg-indigo-600 text-white py-2 rounded-lg hover:bg-indigo-700 font-semibold">
          Continue to Catalog →
        </button>`;
    } else {
      okEl.textContent = `✓ ${id} registered successfully!`;
      setTimeout(() => { closeRegister(); loadAll(); }, 1500);
    }
    okEl.classList.remove('hidden');
    submitBtn.textContent = 'Register';
    submitBtn.disabled = false;
  } catch(err) {
    submitBtn.textContent = 'Register';
    submitBtn.disabled = false;
    errEl.textContent = 'Registration failed: ' + (err.message || err);
    errEl.classList.remove('hidden');
  }
}

// (seed modal removed — use scripts/demo_start.py to reset demo state)

// ============================================================
// APPROVAL ACTIONS
// ============================================================
async function approveAgent(agentId) {
  if (!confirm(`Approve ${agentId}?`)) return;
  try {
    await api(`/api/agents/${agentId}/approve`, 'POST', { decision: 'approve', notes: 'Approved via UI' });
    alert('Agent approved!');
    closeDetail();
    loadAll();
  } catch(e) {
    alert('Failed to approve: ' + e.message);
  }
}

async function rejectAgent(agentId) {
  const notes = prompt(`Reject ${agentId}? Enter reason:`);
  if (!notes) return;
  try {
    await api(`/api/agents/${agentId}/approve`, 'POST', { decision: 'reject', notes });
    alert('Agent rejected!');
    closeDetail();
    loadAll();
  } catch(e) {
    alert('Failed to reject: ' + e.message);
  }
}

// ============================================================
// API HELPER
// ============================================================
async function api(url, method='GET', body=null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const resp = await fetch(url, opts);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def ui():
    return HTMLResponse(content=HTML)


# ---------------------------------------------------------------------------
# Background governance scanner
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def start_governance_scanner():
    """Start background task to scan for unreviewed agents."""
    asyncio.create_task(governance_scan_loop())

async def governance_scan_loop():
    """Continuously scan A2A registry for agents without governance review."""
    await asyncio.sleep(10)  # Wait 10s on startup
    while True:
        try:
            await scan_and_review_agents()
        except Exception as e:
            logger.error(f"Governance scan failed: {e}")
        await asyncio.sleep(60)  # Scan every 60 seconds

async def scan_and_review_agents():
    """Detect agents in A2A registry without governance review and trigger review."""
    raw_agents = await a2a.get_agents()
    enrichments = sqlite_store.all()
    
    for agent in raw_agents:
        agent_id = agent.get("agent_id")
        if not agent_id:
            continue
            
        enr = enrichments.get(agent_id, {})
        
        # Create enrichment for newly detected agents
        if not enr:
            logger.warning(f"⚠️  Auto-detected agent bypassed marketplace: {agent_id}")
            sqlite_store.save(agent_id, {
                "owner_team": agent.get("owner_team", "Unassigned"),
                "source_repo": agent.get("source_repo", ""),
                "description": agent.get("description", "Auto-detected agent (registered directly with A2A server)"),
                "status": "pending_review",
                "item_type": "agent",
                "registered_at": datetime.utcnow().strftime("%Y-%m-%d"),
                "discovery_method": "auto_detected",
                "compliance": [],
            })
            sqlite_store.log_action(agent_id, "auto_detected", "system", {"source": "a2a_registry"})
            enr = sqlite_store.get(agent_id)
        
        # Trigger governance review if missing
        if not enr.get("ai_review"):
            logger.info(f"Running governance review for {agent_id}...")
            
            source_repo = enr.get("source_repo", "")
            if not source_repo:
                # No source repo - create warning review
                sqlite_store.save(agent_id, {
                    "ai_review": {
                        "summary": "⚠️ Agent registered without source repository. Cannot perform code-based governance review.",
                        "requires_human_review": True,
                        "risk_flags": [
                            "No source repository provided",
                            "Bypassed marketplace registration process",
                            "Cannot validate compliance claims"
                        ],
                        "unverified_claims": [],
                        "detected_compliance": [],
                        "recommendations": [
                            "Re-register through marketplace with source_repo URL",
                            "Provide documentation for manual review"
                        ],
                        "confidence": "high",
                        "pci_scope": "unknown",
                        "pii_scope": "unknown",
                        "duplicate_risk": "unknown",
                        "auth_assessment": "Cannot assess without source code"
                    },
                    "ai_reviewed_at": datetime.utcnow().strftime("%Y-%m-%d"),
                    "status": "under_review",
                })
                sqlite_store.log_action(agent_id, "warning_review_created", "system", {"reason": "no_source_repo"})
                continue
            
            # Run full governance review
            try:
                catalog = aggregate_agents(raw_agents) + aggregate_tools(await _get_all_tools())
                source_code = await governance_agent.fetch_source_code(source_repo)
                review = await governance_agent.review(
                    item_id=agent_id,
                    item_type="agent",
                    payload={
                        "agent_id": agent_id,
                        "capabilities": agent.get("capabilities", []),
                        "owner_team": enr.get("owner_team", "Unknown"),
                        "source_repo": source_repo,
                        "description": enr.get("description", ""),
                        "endpoint": agent.get("endpoint", ""),
                        "compliance": enr.get("compliance", []),
                    },
                    existing_catalog=catalog,
                    source_code=source_code,
                )
                if review:
                    has_issues = review.get("requires_human_review") or (review.get("risk_flags") and len(review.get("risk_flags")) > 0)
                    sqlite_store.save(agent_id, {
                        "ai_review": review,
                        "ai_reviewed_at": datetime.utcnow().strftime("%Y-%m-%d"),
                        "status": "under_review" if has_issues else "pending_review",
                    })
                    sqlite_store.log_action(agent_id, "ai_review_completed", "system", {"confidence": review.get("confidence")})
                    logger.info(f"✓ Governance review completed for {agent_id}")
            except Exception as e:
                logger.error(f"Governance review failed for {agent_id}: {e}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8500, reload=True)
