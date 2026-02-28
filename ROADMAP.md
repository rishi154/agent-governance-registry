# Agent Marketplace — Product Roadmap

## Current State (v0.1 — POC)

- Aggregates agents from A2A server (port 9000) and tools from MCP server
- Enrichment store (`enrichments.json`) for governance metadata
- AI governance review on registration (Claude via Vertex AI)
- Keyword-based duplicate detection
- Source repo required for all registrations
- Demo fraud detection agent with real API key enforcement
- Registration CLI script with formatted governance output

---

## Phase 1 — Foundation Hardening
> Make what exists reliable enough to trust

### 1.1 Persistent Backend (replace `enrichments.json`)
- **Problem**: JSON file corrupts under concurrent writes; no query capability; no history
- **Solution**: SQLite (zero-infra, still file-based) or PostgreSQL
- **Tables**: `items`, `enrichments`, `reviews`, `audit_log`
- **Benefit**: Enables all subsequent phases that need history, versioning, and queries

### 1.2 Marketplace Authentication
- **Problem**: Anyone who can reach port 8500 can register or modify agents with no auth
- **Solution**: API key or OAuth2 for the marketplace API itself
- **Scope**: `POST /api/register/*`, `PUT /api/items/*` require auth; `GET` endpoints can stay open
- **Benefit**: Audit trail has an identity, not just a timestamp

### 1.3 Approval Workflow (highest priority governance gap)
- **Problem**: Registration goes live instantly — governance review is advisory only; can be bypassed
- **Flow**: `register → status: pending_review → AI review → human approves → status: active`
- **Rule**: Items where `ai_review.requires_human_review: true` **never** auto-approve
- **UI**: Review queue panel showing pending items with AI review inline
- **Benefit**: This is the answer to "Can a team bypass governance?" — No.

### 1.4 Real Agent Health Monitoring
- **Problem**: Dashboard `health_pct` reads `status == active` from the store — not actual liveness
- **Solution**: Background task pings every registered `endpoint` every 60s
- **States**: `active → degraded (1 failure) → down (3 consecutive failures)`
- **Benefit**: Dashboard reflects reality; owner teams get notified when their agent is down

---

## Phase 2 — Governance Maturity
> The actual value proposition for leadership

### 2.1 Compliance Lifecycle
- **Problem**: PCI-DSS attestations expire annually; no tracking of when compliance was last validated
- **Add fields**: `compliance_reviewed_at`, `compliance_expires_at`, `compliance_evidence_url`
- **Logic**: Surface "Expiring in 30 days" warnings in the UI; trigger re-review before expiry
- **Benefit**: Compliance becomes a living state, not a checkbox set at registration

### 2.2 Human Review Queue UI
- Dedicated `/review-queue` view listing all `pending_review` items
- Shows AI review inline (risk flags, PCI/PII scope, unverified claims)
- Reviewer actions: Approve, Reject (with required note), Request Changes
- All decisions logged: who, when, why

### 2.3 Full Audit Log
- Every event appended to an immutable log: registrations, approvals, rejections, enrichment changes, tool calls via proxy
- Fields: `timestamp`, `actor`, `action`, `item_id`, `before`, `after`
- Essential for PCI-DSS — you must prove who changed what and when
- Exposed as `GET /api/audit-log?item_id=&actor=&from=&to=`

### 2.4 Role-Based Access Control (RBAC)
- **Problem**: `token_vault_lookup` (resolves PANs) is currently discoverable by every team
- **Model**: Teams have roles; items have `visibility` (public, restricted, internal-only)
- **Enforcement**: Items with `Internal-Only` compliance tag only visible to their owner team + admins
- **Admin UI**: Assign team roles, manage item visibility

### 2.5 Contract Drift Detection
- **Problem**: Agent code changes after registration; registered capabilities no longer match actual behaviour
- **Trigger**: GitHub webhook `POST /api/webhooks/github` on push to main
- **Action**: Re-fetch source code, re-run governance review, diff against stored review
- **Alert**: If capabilities grew or risk profile increased — flag for human review
- **Benefit**: The marketplace stays in sync with code automatically

---

## Phase 3 — Developer Platform
> Make teams want to use this, not work around it

### 3.1 Consumer Subscriptions
- Teams declare which agents/tools they depend on
- When a dependency is deprecated, goes down, or has a breaking change → notify the consuming team
- Enables impact analysis: "If I deprecate `score_transaction`, which teams break?"
- API: `POST /api/subscriptions`, `GET /api/subscriptions?team=`

### 3.2 Dependency Graph
- Visualise which tools an agent uses; which agents a team depends on
- Answers: "What is the blast radius if the fraud agent goes down?"
- Especially important for chained agents (agent A → agent B → tool C)
- Rendered as an interactive network diagram in the UI

### 3.3 API Spec Storage
- Store the actual OpenAPI/AsyncAPI spec alongside the registration, not just a description
- Auto-generate "Try It Live" from the spec — no more manual `example_request` fields
- Spec diff on update → auto-generated changelog entry
- `PUT /api/items/{id}/spec` endpoint

### 3.4 CI/CD Integration
- GitHub Action: on merge to `main`, auto-call `POST /api/register/agent` or `PUT /api/items/{id}`
- No manual registration step; the marketplace stays in sync with code
- Prevents "registered 6 months ago, code changed 20 times since" drift
- Template action YAML shipped with the marketplace

### 3.5 Environment Promotion Workflow
- Formally model: `dev → staging → prod` promotion
- An agent must pass governance review in staging before it can be promoted to prod
- The `sandbox_endpoint` / `endpoint` distinction becomes enforced, not advisory
- "Production-Ready" compliance tag only grantable after successful prod promotion

---

## Phase 4 — Intelligence Layer
> Close the loop between what agents claim and what they actually do

### 4.1 Continuous AI Monitoring
- Re-run governance review on a schedule (weekly) against the current source repo HEAD
- Compare new review against stored one — flag if risk profile increased
- "This agent was PCI scope: none at registration, now scope: confirmed — something changed"
- Generates `drift_alerts` visible in the review queue

### 4.2 Runtime Behaviour Analysis
- Log all calls proxied through `/api/proxy` and `/api/invoke-agent`
- AI analyses call patterns: Is this tool being called with PAN-like data even though it claims no PCI scope?
- Anomaly detection: a tool called 50× more than its 30-day baseline
- Real-time alerting to the security team

### 4.3 Usage Analytics & Cost Attribution
- Which team calls which agent, how often, with what latency and error rate
- If agents have usage-based pricing, charge-back to the consuming team's cost centre
- Leadership metric: "We prevented 4 teams from rebuilding fraud scoring — saving estimated $X"
- Dashboard: Top consumers, most depended-on agents, underused (candidate for deprecation)

### 4.4 Proactive Risk Intelligence
- CVE monitoring on agent dependencies (parse `requirements.txt`, `package.json` from source repo)
- "The `fraud_detection_agent` depends on `cryptography==38.0.0` which has a known CVE — auto-issue raised"
- Regulatory change alerts: "New PCI-DSS 4.0 requirement affects agents tagged PCI-Scoped"
- Automated issue creation in the agent's source repository

---

## Interoperability — Framework Support

The marketplace is **framework-agnostic by design**. See [INTEROPERABILITY.md](INTEROPERABILITY.md) for detailed compatibility notes.

| Framework | Discovery | Tool Invocation | A2A Messaging | Notes |
|-----------|-----------|-----------------|----------------|-------|
| Google ADK | ✅ | ✅ | ✅ | Native HTTP endpoints; A2A protocol originated from Google |
| LangChain / LangGraph | ✅ | ✅ | ✅ | Wrap agent in FastAPI; expose `/receive` |
| CrewAI | ✅ | ✅ | ✅ | Same — HTTP wrapper |
| AutoGen | ✅ | ✅ | ✅ | Same — HTTP wrapper |
| Vertex AI Agent Engine | ✅ (metadata) | ⚠️ | ⚠️ | Cloud-hosted; endpoint not always directly accessible |
| AWS Bedrock Agents | ✅ (metadata) | ⚠️ | ⚠️ | Requires HTTP proxy/wrapper |
| OpenAI Assistants | ✅ (metadata) | ⚠️ | ❌ | No persistent endpoint; polling model |
| rsagenticai | ✅ | ✅ | ✅ | Native — already uses same Vertex AI stack |

---

## Quick Wins (Do Now, High Visibility)

| What | Why | Effort |
|------|-----|--------|
| Pending approval state | Shows governance isn't rubber-stamping | Low |
| SQLite migration | Concurrent-write safety, unlocks history | Low–Medium |
| Compliance expiry dates on existing items | Immediate demo value for leadership | Very Low |
| Real health check polling | Dashboard `health_pct` becomes meaningful | Low |
| GitHub webhook endpoint | Auto-triggers re-review on code push | Medium |
| RBAC for `Internal-Only` items | Closes the most critical security gap | Medium |

---

## Non-Goals (Explicit Descoping)

- **Agent execution environment**: The marketplace governs and discovers agents; it does not run them
- **Billing/payments**: Usage attribution is reported; actual billing is handled by Finance systems
- **Model serving**: The marketplace does not host ML models; it catalogues agents that do
- **Cross-cloud federation**: Single-cloud (GCP) for the POC; federation is a future consideration
