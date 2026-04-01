"""
Credit Decision Agent — Demo (INTENTIONALLY FLAWED)

This agent is designed to trigger governance violations across all 25 checks.
DO NOT use this as a template for real agents.

Governance issues planted:
- Hardcoded OpenAI API key (check 6, 12)
- Sends full PII to OpenAI in prompts (check 7, 23)
- No rate limiting (check 8)
- eval() on LLM output (check 9)
- Calls fraud agent with no cycle detection (check 10)
- No token counting or cost limits (check 11)
- No auth on decision endpoint (check 12)
- Unpinned dependencies (check 13)
- print() instead of structured logging (check 14)
- No input validation on raw endpoint (check 15)
- Auto-declines with no human review (check 16)
- No model card or limitations documented (check 17)
- No output guardrails (check 18)
- Uses zip code as proxy variable for risk (check 19)
- No decision logging or reasoning traces (check 20)
- No RAG source validation (check 21)
- No fallback when OpenAI is down (check 22)
- Full customer records in prompts (check 23)
- No AI disclosure to applicants (check 24)
- Floating model version "gpt-4" (check 25)

Run: python agent.py → http://localhost:8201
"""

import os
import json
import random
import httpx
import uvicorn
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from typing import Optional

# ⚠️ GOVERNANCE VIOLATION: Hardcoded API key (checks 6, 12)
OPENAI_API_KEY = "sk-demo-FAKE-key-do-not-use-1234567890abcdef"

# ⚠️ GOVERNANCE VIOLATION: Floating model version (check 25)
MODEL = "gpt-4"

AGENT_ID = "credit_decision_agent"
AGENT_TYPE = "lending"
AGENT_PORT = 8201
AGENT_DID = "did:key:z6MkCreditDecisionXYZ010"
AGENT_ENDPOINT = f"http://localhost:{AGENT_PORT}/receive"
A2A_SERVER_URL = "http://localhost:9000"
MARKETPLACE_URL = "http://localhost:8500"
SOURCE_REPO = "https://github.com/rishi154/credit-decision-agent"

CAPABILITIES = [
    "evaluate_credit_application",
    "auto_decline",
    "pull_credit_report",
    "calculate_risk_score",
]

app = FastAPI(title="Credit Decision Agent", version="0.1.0")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class CreditApplication(BaseModel):
    applicant_name: str
    ssn: str
    email: str
    phone: str
    date_of_birth: str
    address: str
    zip_code: str
    annual_income: float
    requested_amount: float
    employment_status: str

class A2AMessage(BaseModel):
    from_did: str
    to_did: str
    message_type: str
    body: dict
    signature: str


# ---------------------------------------------------------------------------
# "AI" credit evaluation
# ---------------------------------------------------------------------------

def call_openai(prompt: str) -> str:
    """
    ⚠️ GOVERNANCE VIOLATIONS:
    - Hardcoded API key (check 6)
    - Full PII in prompt (check 23)
    - No timeout (check 8)
    - No token counting (check 11)
    - Floating model version (check 25)
    - No error handling / fallback (check 22)
    """
    # In demo mode, simulate the LLM response instead of calling OpenAI
    # The governance scanner will still flag the code patterns
    print(f"[LLM] Sending prompt to {MODEL} ({len(prompt)} chars)")
    print(f"[LLM] Prompt contains: {prompt[:200]}...")

    # Simulated LLM response
    return json.dumps({
        "decision": random.choice(["approve", "decline", "decline", "review"]),
        "risk_score": random.randint(200, 850),
        "reasoning": "Based on credit history and income analysis",
        "max_approved_amount": random.randint(1000, 50000),
    })


def calculate_zip_risk(zip_code: str) -> float:
    """
    ⚠️ GOVERNANCE VIOLATION: Uses zip code as proxy variable (check 19)
    Zip codes correlate with race and ethnicity — this creates
    disparate impact in lending decisions.
    """
    high_risk_zips = ["10001", "60601", "90001", "30301", "77001"]
    medium_risk_zips = ["85001", "32801", "97201"]

    if zip_code in high_risk_zips:
        return 0.8
    elif zip_code in medium_risk_zips:
        return 0.5
    return 0.2


# ---------------------------------------------------------------------------
# Endpoints — ⚠️ No auth on sensitive decision endpoint (check 12)
# ---------------------------------------------------------------------------

@app.post("/tools/evaluate_credit")
async def evaluate_credit(app_data: CreditApplication):
    """
    Evaluate a credit application using AI.

    ⚠️ GOVERNANCE VIOLATIONS:
    - No authentication (check 12)
    - No rate limiting (check 8)
    - Sends full PII to LLM (check 23)
    - No human-in-the-loop (check 16)
    - No guardrails on output (check 18)
    - No AI disclosure (check 24)
    - No decision audit trail (check 20)
    - Uses zip code risk scoring (check 19)
    """

    # ⚠️ VIOLATION: Log full PII (check 7)
    print(f"Processing application for {app_data.applicant_name}, SSN: {app_data.ssn}")
    print(f"Email: {app_data.email}, Phone: {app_data.phone}, DOB: {app_data.date_of_birth}")

    # ⚠️ VIOLATION: Full PII sent to LLM provider (check 23)
    prompt = f"""Evaluate this credit application and return a JSON decision.

Applicant: {app_data.applicant_name}
SSN: {app_data.ssn}
Date of Birth: {app_data.date_of_birth}
Address: {app_data.address}
Email: {app_data.email}
Phone: {app_data.phone}
Annual Income: ${app_data.annual_income:,.2f}
Requested Amount: ${app_data.requested_amount:,.2f}
Employment: {app_data.employment_status}

Return JSON with: decision (approve/decline/review), risk_score (200-850),
reasoning (string), max_approved_amount (number).
"""

    llm_response = call_openai(prompt)

    # ⚠️ VIOLATION: eval() on LLM output (check 9)
    try:
        result = eval(llm_response)
    except Exception:
        result = json.loads(llm_response)

    # ⚠️ VIOLATION: Zip code as proxy variable (check 19)
    zip_risk = calculate_zip_risk(app_data.zip_code)
    if zip_risk > 0.6:
        result["risk_score"] = max(result.get("risk_score", 500) - 150, 200)
        if result.get("decision") == "approve":
            result["decision"] = "review"

    # ⚠️ VIOLATION: Auto-decline with no human review (check 16)
    if result.get("risk_score", 500) < 400:
        result["decision"] = "decline"
        result["reasoning"] = "Automatically declined due to low risk score"
        # No escalation, no human review, no appeal path

    # ⚠️ VIOLATION: No guardrails — raw LLM reasoning returned (check 18)
    # ⚠️ VIOLATION: No AI disclosure — applicant doesn't know AI decided (check 24)
    return {
        "application_id": f"APP-{random.randint(10000, 99999)}",
        "applicant_name": app_data.applicant_name,  # ⚠️ PII in response
        "ssn_last_four": app_data.ssn[-4:],
        **result,
        "zip_risk_factor": zip_risk,
    }


@app.post("/tools/pull_credit_report")
async def pull_credit_report(ssn: str = "", name: str = ""):
    """Pull credit report by SSN. No auth required."""
    # ⚠️ VIOLATION: No input validation (check 15)
    # ⚠️ VIOLATION: No auth (check 12)
    print(f"Pulling credit report for SSN: {ssn}")
    return {
        "ssn": ssn,
        "name": name,
        "credit_score": random.randint(300, 850),
        "accounts": random.randint(2, 15),
        "delinquencies": random.randint(0, 5),
        "bankruptcies": random.randint(0, 1),
        "hard_inquiries_12m": random.randint(0, 8),
    }


@app.post("/tools/auto_decline")
async def auto_decline(application_id: str = "", reason: str = ""):
    """
    Automatically decline an application. No human review.
    ⚠️ VIOLATION: Autonomous irreversible financial decision (check 16)
    """
    # ⚠️ VIOLATION: Calls fraud agent without cycle detection (check 10)
    try:
        async with httpx.AsyncClient() as client:  # ⚠️ No timeout (check 8)
            resp = await client.post(
                "http://localhost:8101/tools/score_transaction",
                json={"transaction_id": application_id, "amount": 0, "merchant_id": "INTERNAL"},
                headers={"X-API-Key": "demo-key-12345"},
            )
            fraud_data = resp.json()
    except Exception:
        fraud_data = {}

    print(f"Auto-declined application {application_id}: {reason}")
    return {
        "application_id": application_id,
        "status": "declined",
        "reason": reason,
        "fraud_check": fraud_data,
        "appeal_available": False,  # ⚠️ No appeal mechanism
    }


# ---------------------------------------------------------------------------
# A2A message receiver
# ---------------------------------------------------------------------------

@app.post("/receive")
async def receive_message(message: A2AMessage):
    print(f"A2A message: {message.message_type}")
    try:
        if message.message_type == "evaluate_credit_application":
            return await evaluate_credit(CreditApplication(**message.body))
        elif message.message_type == "pull_credit_report":
            return await pull_credit_report(**message.body)
        elif message.message_type == "auto_decline":
            return await auto_decline(**message.body)
        else:
            return {"status": "unknown_capability", "type": message.message_type}
    except Exception as e:
        # ⚠️ VIOLATION: Exception details leaked (check 15)
        return {"status": "error", "message": str(e), "type": str(type(e))}


# No /health endpoint (check 14)


# ---------------------------------------------------------------------------
# Self-registration
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def register():
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            await client.post(f"{A2A_SERVER_URL}/agents/register", json={
                "agent_id": AGENT_ID,
                "agent_type": AGENT_TYPE,
                "endpoint": AGENT_ENDPOINT,
                "did": AGENT_DID,
                "public_key": "demo-public-key-credit",
                "capabilities": CAPABILITIES,
            })
            print(f"A2A registration: OK")
        except Exception as e:
            print(f"A2A server not reachable: {e}")

        try:
            await client.post(f"{MARKETPLACE_URL}/api/register/agent", json={
                "agent_id": AGENT_ID,
                "agent_type": AGENT_TYPE,
                "endpoint": AGENT_ENDPOINT,
                "capabilities": CAPABILITIES,
                "owner_team": "Consumer Lending",
                "compliance": ["PII-Safe", "Production-Ready"],  # ⚠️ False claims
                "docs_url": "",
                "source_repo": SOURCE_REPO,
                "description": (
                    "AI-powered credit decisioning agent. Evaluates credit applications "
                    "using GPT-4, pulls credit reports, and auto-declines high-risk "
                    "applicants. Uses applicant name, SSN, address, and income data."
                ),
            })
            print("Marketplace registration: OK")
        except Exception as e:
            print(f"Marketplace not reachable: {e}")

        # Register tools
        tools = [
            {
                "tool_id": "evaluate_credit",
                "description": "AI-powered credit application evaluation. Sends full applicant data to GPT-4 for risk assessment.",
                "owner_team": "Consumer Lending",
                "compliance": ["PII-Safe"],
                "source_repo": SOURCE_REPO,
                "source_agent": AGENT_ID,
                "endpoint": f"http://localhost:{AGENT_PORT}/tools/evaluate_credit",
                "example_request": {
                    "applicant_name": "Jane Doe",
                    "ssn": "123-45-6789",
                    "email": "jane@example.com",
                    "phone": "555-0100",
                    "date_of_birth": "1990-01-15",
                    "address": "123 Main St, Anytown, US",
                    "zip_code": "10001",
                    "annual_income": 85000,
                    "requested_amount": 25000,
                    "employment_status": "employed_full_time",
                },
            },
            {
                "tool_id": "pull_credit_report",
                "description": "Pulls credit report by SSN. Returns score, accounts, delinquencies.",
                "owner_team": "Consumer Lending",
                "compliance": ["PII-Safe"],
                "source_repo": SOURCE_REPO,
                "source_agent": AGENT_ID,
                "endpoint": f"http://localhost:{AGENT_PORT}/tools/pull_credit_report",
                "example_request": {"ssn": "123-45-6789", "name": "Jane Doe"},
            },
        ]
        for tool in tools:
            try:
                await client.post(f"{MARKETPLACE_URL}/api/register/tool", json=tool)
                print(f"Tool registered: {tool['tool_id']}")
            except Exception as e:
                print(f"Could not register tool {tool['tool_id']}: {e}")


if __name__ == "__main__":
    print(f"Starting {AGENT_ID} on port {AGENT_PORT}")
    uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT)
