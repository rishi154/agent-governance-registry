"""
Seeds realistic payment processor demo data into the live MCP and A2A servers,
and saves enrichment metadata locally.
Call via POST /api/seed on the marketplace app.
"""

import httpx
import logging
from datetime import datetime
from src.marketplace import enrichment_store

logger = logging.getLogger(__name__)

MCP_BASE = "http://localhost:9595"
A2A_BASE = "http://localhost:9000"
TIMEOUT = 5.0

# ---------------------------------------------------------------------------
# Demo agents — registered to A2A server
# ---------------------------------------------------------------------------
DEMO_AGENTS = [
    {
        "registration": {
            "agent_id": "fraud_detection_agent",
            "agent_type": "risk",
            "endpoint": "http://localhost:8101/receive",
            "did": "did:key:z6MkFraudDetectXYZ001",
            "public_key": "demo-public-key-fraud",
            "capabilities": ["real_time_fraud_scoring", "transaction_anomaly_detection", "velocity_check"],
        },
        "enrichment": {
            "owner_team": "Risk & Fraud",
            "compliance": ["PCI-Scoped", "Production-Ready"],
            "docs_url": "https://wiki.internal/agents/fraud-detection",
            "status": "active",
            "item_type": "agent",
            "description": "Real-time fraud scoring agent using ML models to detect anomalous transactions before authorization.",
            "registered_at": "2026-01-10",
        },
    },
    {
        "registration": {
            "agent_id": "chargeback_processing_agent",
            "agent_type": "disputes",
            "endpoint": "http://localhost:8102/receive",
            "did": "did:key:z6MkChargebackXYZ002",
            "public_key": "demo-public-key-chargeback",
            "capabilities": ["chargeback_intake", "evidence_collection", "dispute_routing", "Visa_MC_arbitration"],
        },
        "enrichment": {
            "owner_team": "Disputes & Chargebacks",
            "compliance": ["PCI-Scoped", "Production-Ready"],
            "docs_url": "https://wiki.internal/agents/chargeback",
            "status": "active",
            "item_type": "agent",
            "description": "Automates chargeback lifecycle from intake through evidence gathering and network submission.",
            "registered_at": "2026-01-12",
        },
    },
    {
        "registration": {
            "agent_id": "kyc_verification_agent",
            "agent_type": "onboarding",
            "endpoint": "http://localhost:8103/receive",
            "did": "did:key:z6MkKYCVerifyXYZ003",
            "public_key": "demo-public-key-kyc",
            "capabilities": ["identity_verification", "document_validation", "watchlist_screening", "risk_scoring"],
        },
        "enrichment": {
            "owner_team": "Merchant Onboarding",
            "compliance": ["PII-Safe", "Production-Ready"],
            "docs_url": "https://wiki.internal/agents/kyc",
            "status": "active",
            "item_type": "agent",
            "description": "KYC/KYB verification agent that validates merchant identities against government databases and watchlists.",
            "registered_at": "2026-01-15",
        },
    },
    {
        "registration": {
            "agent_id": "aml_screening_agent",
            "agent_type": "compliance",
            "endpoint": "http://localhost:8104/receive",
            "did": "did:key:z6MkAMLScreenXYZ004",
            "public_key": "demo-public-key-aml",
            "capabilities": ["aml_transaction_monitoring", "suspicious_activity_reporting", "ofac_screening"],
        },
        "enrichment": {
            "owner_team": "Compliance & Regulatory",
            "compliance": ["PCI-Scoped", "PII-Safe", "Production-Ready"],
            "docs_url": "https://wiki.internal/agents/aml-screening",
            "status": "active",
            "item_type": "agent",
            "description": "AML transaction monitoring agent that flags suspicious patterns and generates SAR reports for FinCEN.",
            "registered_at": "2026-01-18",
        },
    },
    {
        "registration": {
            "agent_id": "merchant_risk_agent",
            "agent_type": "underwriting",
            "endpoint": "http://localhost:8105/receive",
            "did": "did:key:z6MkMerchantRiskXYZ005",
            "public_key": "demo-public-key-merchant",
            "capabilities": ["merchant_risk_scoring", "credit_underwriting", "portfolio_monitoring"],
        },
        "enrichment": {
            "owner_team": "Merchant Underwriting",
            "compliance": ["PCI-Scoped", "Internal-Only"],
            "docs_url": "https://wiki.internal/agents/merchant-risk",
            "status": "active",
            "item_type": "agent",
            "description": "Evaluates merchant risk profiles during onboarding and monitors ongoing portfolio health.",
            "registered_at": "2026-01-20",
        },
    },
]

# ---------------------------------------------------------------------------
# Demo tools — registered to MCP server enrichments only
# (MCP tool registration is code-driven, not API-driven, so we store enrichments)
# ---------------------------------------------------------------------------
DEMO_TOOLS = [
    {
        "tool_id": "transaction_lookup",
        "enrichment": {
            "owner_team": "Core Payments",
            "compliance": ["PCI-Scoped", "Production-Ready"],
            "docs_url": "https://wiki.internal/tools/transaction-lookup",
            "status": "active",
            "item_type": "tool",
            "description": "Retrieves full transaction detail by transaction ID, including auth, clearing, and settlement records.",
            "registered_at": "2026-01-08",
        },
    },
    {
        "tool_id": "pci_data_masking",
        "enrichment": {
            "owner_team": "Security Engineering",
            "compliance": ["PCI-Scoped", "Production-Ready"],
            "docs_url": "https://wiki.internal/tools/pci-masking",
            "status": "active",
            "item_type": "tool",
            "description": "Masks PAN, CVV, and sensitive cardholder data fields in logs, reports, and API responses.",
            "registered_at": "2026-01-09",
        },
    },
    {
        "tool_id": "currency_conversion",
        "enrichment": {
            "owner_team": "FX & Treasury",
            "compliance": ["Production-Ready"],
            "docs_url": "https://wiki.internal/tools/currency-conversion",
            "status": "active",
            "item_type": "tool",
            "description": "Converts transaction amounts across 150+ currencies using live exchange rates from the FX rate service.",
            "registered_at": "2026-01-14",
        },
    },
    {
        "tool_id": "settlement_calculator",
        "enrichment": {
            "owner_team": "Core Payments",
            "compliance": ["PCI-Scoped", "Production-Ready"],
            "docs_url": "https://wiki.internal/tools/settlement-calc",
            "status": "active",
            "item_type": "tool",
            "description": "Calculates net settlement amounts after interchange, assessments, and processor fees for merchant funding.",
            "registered_at": "2026-01-16",
        },
    },
    {
        "tool_id": "token_vault_lookup",
        "enrichment": {
            "owner_team": "Tokenization Platform",
            "compliance": ["PCI-Scoped", "Production-Ready"],
            "docs_url": "https://wiki.internal/tools/token-vault",
            "status": "active",
            "item_type": "tool",
            "description": "Resolves payment tokens to underlying PANs via the secure token vault. Restricted to authorized services.",
            "registered_at": "2026-01-22",
        },
    },
]


async def seed_demo_data() -> dict:
    """
    Registers demo agents to A2A server and saves all enrichments locally.
    Returns a summary of what was created.
    """
    results = {"agents_registered": [], "agents_failed": [], "tools_enriched": [], "errors": []}

    # Register agents to A2A server
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for item in DEMO_AGENTS:
            agent_id = item["registration"]["agent_id"]
            try:
                resp = await client.post(f"{A2A_BASE}/agents/register", json=item["registration"])
                if resp.status_code in (200, 201):
                    results["agents_registered"].append(agent_id)
                elif resp.status_code == 409:
                    results["agents_registered"].append(f"{agent_id} (already exists)")
                else:
                    results["agents_failed"].append(f"{agent_id}: HTTP {resp.status_code}")
            except Exception as e:
                results["agents_failed"].append(f"{agent_id}: {str(e)}")

            # Always save enrichment regardless of A2A result
            enrichment_store.save(agent_id, item["enrichment"])

    # Save tool enrichments (MCP tools are code-registered, not API-registered)
    for item in DEMO_TOOLS:
        tool_id = item["tool_id"]
        enrichment_store.save(tool_id, item["enrichment"])
        results["tools_enriched"].append(tool_id)

    return results
