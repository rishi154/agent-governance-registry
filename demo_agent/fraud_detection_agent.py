"""
Fraud Detection Agent — Demo
Follows the ap2_a2a_server agent_template.py pattern.

This agent self-registers with the A2A server on startup and
registers its tools with the Agent Marketplace.

Run: python demo_agent/fraud_detection_agent.py
     → http://localhost:8101
"""

import random
import logging
import httpx
import uvicorn
from fastapi import FastAPI, Header, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
AGENT_ID       = "fraud_detection_agent"
AGENT_TYPE     = "risk"
AGENT_PORT     = 8101
AGENT_DID      = "did:key:z6MkFraudDetectXYZ001"
AGENT_ENDPOINT = f"http://localhost:{AGENT_PORT}/receive"
A2A_SERVER_URL = "http://localhost:9000"
MARKETPLACE_URL = "http://localhost:8500"
SOURCE_REPO    = "https://github.com/payments-platform/fraud-detection-agent"

CAPABILITIES = [
    "score_transaction",
    "velocity_check",
    "merchant_risk_lookup",
]

# API key required for all tool endpoints
VALID_API_KEY = "demo-key-12345"

def require_api_key(x_api_key: str = Header(..., description="API key for tool access")):
    if x_api_key != VALID_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key header")

app = FastAPI(title="Fraud Detection Agent", version="1.0.0")


# ---------------------------------------------------------------------------
# Tool input models
# ---------------------------------------------------------------------------

class ScoreTransactionRequest(BaseModel):
    transaction_id: str
    amount: float
    merchant_id: str
    card_country: Optional[str] = "US"
    merchant_country: Optional[str] = "US"

class VelocityCheckRequest(BaseModel):
    card_id: str
    time_window_minutes: int = 60

class MerchantRiskRequest(BaseModel):
    merchant_id: str

class A2AMessage(BaseModel):
    from_did: str
    to_did: str
    message_type: str
    body: dict
    signature: str


# ---------------------------------------------------------------------------
# Tool endpoints — these are the actual capabilities of this agent
# ---------------------------------------------------------------------------

@app.post("/tools/score_transaction", dependencies=[Depends(require_api_key)])
async def score_transaction(req: ScoreTransactionRequest):
    """
    Returns a real-time fraud risk score for a transaction.
    Score: 0 (clean) to 100 (high risk). Recommendation: approve / review / decline.
    """
    # Mock ML scoring logic
    base_score = random.randint(5, 30)

    # Risk signals
    if req.amount > 5000:
        base_score += 25
    if req.card_country != req.merchant_country:
        base_score += 20
    if req.merchant_id.startswith("MHIGH"):
        base_score += 30

    score = min(base_score, 100)
    if score < 30:
        recommendation = "approve"
    elif score < 65:
        recommendation = "review"
    else:
        recommendation = "decline"

    logger.info(f"Scored txn {req.transaction_id}: {score} → {recommendation}")
    return {
        "transaction_id": req.transaction_id,
        "risk_score": score,
        "recommendation": recommendation,
        "signals": {
            "high_amount": req.amount > 5000,
            "cross_border": req.card_country != req.merchant_country,
            "high_risk_merchant": req.merchant_id.startswith("MHIGH"),
        }
    }


@app.post("/tools/velocity_check", dependencies=[Depends(require_api_key)])
async def velocity_check(req: VelocityCheckRequest):
    """
    Checks how many transactions a card has made in the given time window.
    Flags if count exceeds risk thresholds.
    """
    # Mock velocity data
    txn_count = random.randint(1, 15)
    amount_total = round(random.uniform(20, 3000), 2)
    threshold = 10
    flagged = txn_count > threshold

    logger.info(f"Velocity check for card {req.card_id[-4:]}: {txn_count} txns in {req.time_window_minutes}m")
    return {
        "card_id": req.card_id,
        "time_window_minutes": req.time_window_minutes,
        "transaction_count": txn_count,
        "total_amount": amount_total,
        "threshold": threshold,
        "velocity_flagged": flagged,
        "risk_level": "high" if flagged else "normal",
    }


@app.post("/tools/merchant_risk_lookup", dependencies=[Depends(require_api_key)])
async def merchant_risk_lookup(req: MerchantRiskRequest):
    """
    Returns the risk profile for a merchant based on historical data.
    Includes chargeback rate, dispute history, and risk tier.
    """
    # Mock merchant risk data
    tiers = {
        "MHIGH": {"tier": "high", "chargeback_rate": 2.8, "dispute_count": 47},
        "MMED":  {"tier": "medium", "chargeback_rate": 0.9, "dispute_count": 12},
    }
    prefix = req.merchant_id[:5] if len(req.merchant_id) >= 5 else "MLOW0"
    profile = tiers.get(prefix, {"tier": "low", "chargeback_rate": 0.3, "dispute_count": 2})

    logger.info(f"Merchant risk lookup: {req.merchant_id} → tier={profile['tier']}")
    return {
        "merchant_id": req.merchant_id,
        "risk_tier": profile["tier"],
        "chargeback_rate_pct": profile["chargeback_rate"],
        "dispute_count_90d": profile["dispute_count"],
        "on_watchlist": profile["tier"] == "high",
        "recommendation": "manual_review" if profile["tier"] in ("high", "medium") else "auto_approve",
    }


# ---------------------------------------------------------------------------
# A2A message receiver
# ---------------------------------------------------------------------------

@app.post("/receive")
async def receive_message(message: A2AMessage):
    """Receive and route A2A messages to the appropriate tool."""
    logger.info(f"A2A message received: {message.message_type}")

    try:
        if message.message_type == "score_transaction":
            return await score_transaction(ScoreTransactionRequest(**message.body))
        elif message.message_type == "velocity_check":
            return await velocity_check(VelocityCheckRequest(**message.body))
        elif message.message_type == "merchant_risk_lookup":
            return await merchant_risk_lookup(MerchantRiskRequest(**message.body))
        else:
            return {"status": "unknown_message_type", "type": message.message_type}
    except Exception as e:
        logger.error(f"Error handling message {message.message_type}: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/health")
async def health():
    return {"status": "ok", "agent_id": AGENT_ID, "capabilities": CAPABILITIES}


# ---------------------------------------------------------------------------
# Self-registration on startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def register():
    async with httpx.AsyncClient(timeout=5.0) as client:
        # 1. Register with A2A server
        try:
            resp = await client.post(f"{A2A_SERVER_URL}/agents/register", json={
                "agent_id": AGENT_ID,
                "agent_type": AGENT_TYPE,
                "endpoint": AGENT_ENDPOINT,
                "did": AGENT_DID,
                "public_key": "demo-public-key-fraud",
                "capabilities": CAPABILITIES,
            })
            logger.info(f"A2A registration: {resp.status_code}")
        except Exception as e:
            logger.warning(f"A2A server not reachable: {e}")

        # 2. Register agent enrichment with marketplace
        try:
            await client.post(f"{MARKETPLACE_URL}/api/register/agent", json={
                "agent_id": AGENT_ID,
                "agent_type": AGENT_TYPE,
                "endpoint": AGENT_ENDPOINT,
                "capabilities": CAPABILITIES,
                "owner_team": "Risk & Fraud",
                "compliance": ["PCI-Scoped", "Production-Ready"],
                "docs_url": "https://wiki.internal/agents/fraud-detection",
                "source_repo": SOURCE_REPO,
                "description": "Real-time fraud scoring agent. Provides transaction scoring, velocity checks, and merchant risk lookups.",
            })
            logger.info("Marketplace registration: OK")
        except Exception as e:
            logger.warning(f"Marketplace not reachable: {e}")

        # 3. Register each tool with the marketplace
        tools = [
            {
                "tool_id": "score_transaction",
                "description": "Scores a transaction 0-100 for fraud risk. Returns risk score, recommendation (approve/review/decline), and triggered signals.",
                "owner_team": "Risk & Fraud",
                "compliance": ["PCI-Scoped", "Production-Ready"],
                "docs_url": "https://wiki.internal/agents/fraud-detection#score-transaction",
                "source_repo": SOURCE_REPO,
                "source_agent": AGENT_ID,
                "endpoint": f"http://localhost:{AGENT_PORT}/tools/score_transaction",
                "example_request": {"transaction_id": "TXN-20260228-001", "amount": 7500.00, "merchant_id": "MHIGH-NYC-042", "card_country": "US", "merchant_country": "MX"},
            },
            {
                "tool_id": "velocity_check",
                "description": "Checks transaction velocity for a card in a rolling time window. Flags cards exceeding threshold.",
                "owner_team": "Risk & Fraud",
                "compliance": ["PCI-Scoped", "Production-Ready"],
                "docs_url": "https://wiki.internal/agents/fraud-detection#velocity-check",
                "source_repo": SOURCE_REPO,
                "source_agent": AGENT_ID,
                "endpoint": f"http://localhost:{AGENT_PORT}/tools/velocity_check",
                "example_request": {"card_id": "CARD-4111-XXXX-XXXX-1111", "time_window_minutes": 60},
            },
            {
                "tool_id": "merchant_risk_lookup",
                "description": "Returns risk tier, chargeback rate, and dispute history for a merchant ID.",
                "owner_team": "Risk & Fraud",
                "compliance": ["PCI-Scoped", "Production-Ready"],
                "docs_url": "https://wiki.internal/agents/fraud-detection#merchant-risk",
                "source_repo": SOURCE_REPO,
                "source_agent": AGENT_ID,
                "endpoint": f"http://localhost:{AGENT_PORT}/tools/merchant_risk_lookup",
                "example_request": {"merchant_id": "MHIGH-NYC-042"},
            },
        ]
        for tool in tools:
            try:
                await client.post(f"{MARKETPLACE_URL}/api/register/tool", json=tool)
                logger.info(f"Tool registered: {tool['tool_id']}")
            except Exception as e:
                logger.warning(f"Could not register tool {tool['tool_id']}: {e}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logger.info(f"Starting {AGENT_ID} on port {AGENT_PORT}")
    uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT)
