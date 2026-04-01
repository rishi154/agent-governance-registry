# Demo Agents — Launch Guide

Two demo agents designed to showcase the Agent Marketplace's 25-point governance review.

## The Agents

### 🔴 Credit Decision Agent (port 8201) — "The Bad One"
Intentionally loaded with governance violations:
- Hardcoded OpenAI API key
- Sends full PII (SSN, name, DOB) to LLM in prompts
- Auto-declines credit applications with no human review
- Uses zip code as a proxy variable (bias risk)
- `eval()` on LLM output
- No auth on sensitive endpoints
- No rate limiting, no timeouts, no fallback
- Floating model version (`gpt-4`)
- Unpinned dependencies
- `print()` instead of structured logging
- No health check, no AI disclosure
- Claims "PII-Safe" and "Production-Ready" — both false

### 🟢 KYC Verification Agent (port 8202) — "The Good One"
Demonstrates responsible AI governance:
- API key auth on all endpoints
- Model version pinned via env var
- No PII sent to LLM — only anonymized business context
- Human escalation for low-confidence results
- Output guardrails (blocked topics, PII redaction)
- Full decision audit logging
- Source attribution on watchlist checks
- Rules-based fallback when LLM unavailable
- AI disclosure in every response
- Model card endpoint with limitations documented
- Structured JSON logging
- Health check endpoint
- Pinned dependencies
- Rate limiting

## Quick Start

```bash
# Terminal 1: Start A2A server (must be running first)
cd <a2a-server-dir>
python server.py

# Terminal 2: Start marketplace
cd c:\work\agent-marketplace
python app.py

# Terminal 3: Start the BAD agent
cd c:\work\agent-marketplace\demo_agents\credit-decision-agent
pip install -r requirements.txt
python agent.py

# Terminal 4: Start the GOOD agent
cd c:\work\agent-marketplace\demo_agents\kyc-verification-agent
pip install -r requirements.txt
python agent.py
```

Both agents self-register with the A2A server and marketplace on startup.

## Demo Script

### 1. Show the Dashboard (http://localhost:8500)
- Both agents appear in the catalog
- Both show 🚫 Blocked badges (pending governance review)
- Stats bar shows enforcement counts

### 2. Open Credit Decision Agent → AI Governance Review
Point out the red flags:
- 🔴 **Risk Flags**: Hardcoded API key, PII in prompts, eval() on LLM output
- 🔴 **Human-in-the-Loop**: `required_but_missing` — auto-declines with no human review
- 🔴 **Bias & Fairness**: `at_risk` — uses zip code as proxy variable
- 🔴 **Data Sent to Provider**: `confirmed_exposure` — full SSN/name/DOB in prompts
- 🔴 **Guardrails**: `none` — raw LLM output passed to users
- 🔴 **Model Version**: `floating` — uses "gpt-4" not a pinned version
- 🔴 **Consent**: `missing` — no AI disclosure to applicants
- 🟡 **Unverified Claims**: "PII-Safe" and "Production-Ready" flagged as unverified
- **Requires Human Review**: YES

### 3. Open KYC Verification Agent → AI Governance Review
Point out the green checks:
- 🟢 **Human-in-the-Loop**: `required_and_present` — escalates low-confidence
- 🟢 **Model Transparency**: `comprehensive` — model card with limitations
- 🟢 **Guardrails**: `implemented` — output filtering active
- 🟢 **Bias & Fairness**: `assessed` — fairness tested, no proxy variables
- 🟢 **Explainability**: `comprehensive` — full audit trail
- 🟢 **Data Sent to Provider**: `safe` — only anonymized data
- 🟢 **Consent**: `compliant` — AI disclosure in every response
- 🟢 **Model Version**: `pinned` — via environment variable
- **Requires Human Review**: NO (or minor recommendations only)

### 4. Demonstrate Enforcement
- Try "Try It Live" on Credit Decision Agent → **BLOCKED**
- Show the 403 error: "blocked_by_governance"

### 5. Approve the Good Agent
- Click ✓ Approve on KYC Verification Agent
- Badge changes to ✓ Allowed
- "Try It Live" now works — send a real request

### 6. Reject the Bad Agent
- Click ✗ Reject on Credit Decision Agent
- Enter reason: "Hardcoded API keys, PII sent to LLM, no human review"
- Badge stays 🚫 Blocked

### 7. Show Audit Trail
- `GET /api/agents/kyc_verification_agent/audit` — shows full history
- registered → ai_review_completed → approved

## What Each Check Triggers

| # | Check | Credit Agent | KYC Agent |
|---|-------|-------------|-----------|
| 1 | PCI Scope | none | none |
| 2 | PII Scope | confirmed | possible |
| 3 | Compliance Claims | unverified | verified |
| 6 | LLM/Model Usage | hardcoded key | env var |
| 7 | Data Privacy | logs PII | no PII logged |
| 8 | Rate Limiting | none | implemented |
| 9 | Output Validation | eval() | Pydantic |
| 10 | Agent Chaining | no cycle detection | N/A |
| 11 | Cost Tracking | none | N/A |
| 12 | Auth | none | API key |
| 13 | Dependencies | unpinned | pinned |
| 14 | Observability | print() | structured JSON |
| 15 | Input Validation | none | Pydantic |
| 16 | Human-in-the-Loop | **missing** | present |
| 17 | Model Transparency | **missing** | comprehensive |
| 18 | Guardrails | **none** | implemented |
| 19 | Bias & Fairness | **at_risk** (zip code) | assessed |
| 20 | Explainability | **none** | audit trail |
| 21 | Grounding/RAG | N/A | source attribution |
| 22 | Model Fallback | **fragile** | resilient |
| 23 | Data to Provider | **confirmed PII** | safe (anonymized) |
| 24 | Consent/Disclosure | **missing** | compliant |
| 25 | Version Pinning | **floating** | pinned |
