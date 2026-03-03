# Agent Marketplace — Product Roadmap

## Current State (v1.0 — Production Ready)

✅ **Completed:**
- Aggregates agents from A2A server and tools from MCP server
- **SQLite database** with audit logging (replaced enrichments.json)
- **Approval workflow** (pending_review → under_review → approved/rejected)
- **Authentication & RBAC** (API key-based: viewer, developer, admin)
- **AI governance review** with 15 comprehensive checks (Gemini 2.5 Flash Lite)
- **Background scanner** auto-detects agents registered directly with A2A
- Source code analysis from GitHub repos
- Duplicate detection
- Web UI with approve/reject buttons

---

## Phase 1 — Foundation Hardening ✅ COMPLETE

### 1.1 Persistent Backend ✅
- **Status**: DONE - SQLite with 3 tables (agents, reviews, audit_log)
- **Benefit**: Concurrent-write safety, query capability, full history

### 1.2 Marketplace Authentication ✅
- **Status**: DONE - API key auth with 3 roles
- **Scope**: All write operations require auth; reads optional
- **Benefit**: Full audit trail with actor tracking

### 1.3 Approval Workflow ✅
- **Status**: DONE - Full workflow implemented
- **Flow**: `register → pending_review → AI review → under_review → admin approves/rejects`
- **Rule**: Agents with risk flags require human approval
- **UI**: Approve/Reject buttons in detail panel
- **Benefit**: No bypass possible - all agents reviewed

### 1.4 Real Agent Health Monitoring ⏳
- **Problem**: Dashboard `health_pct` reads `status == active` from store — not actual liveness
- **Solution**: Background task pings every registered `endpoint` every 60s
- **States**: `active → degraded (1 failure) → down (3 consecutive failures)`
- **Priority**: MEDIUM

---

## Phase 2 — Governance Maturity

### 2.1 Compliance Lifecycle ⏳
- **Problem**: PCI-DSS attestations expire annually; no tracking
- **Add fields**: `compliance_reviewed_at`, `compliance_expires_at`, `compliance_evidence_url`
- **Logic**: Surface "Expiring in 30 days" warnings in UI
- **Priority**: HIGH

### 2.2 Enhanced Review Queue UI ⏳
- Dedicated `/review-queue` page (currently API-only)
- Bulk approve/reject actions
- Filter by risk level, team, compliance scope
- **Priority**: MEDIUM

### 2.3 Notifications ⏳
- Slack/email alerts when:
  - New agent needs review
  - Agent approved/rejected
  - Compliance expiring soon
- **Priority**: HIGH

### 2.4 Team-Based RBAC ⏳
- **Problem**: All admins see all agents; no team isolation
- **Model**: Teams own agents; visibility controls (public, team-only, admin-only)
- **Enforcement**: `Internal-Only` agents only visible to owner team + admins
- **Priority**: MEDIUM

### 2.5 Contract Drift Detection ⏳
- **Trigger**: GitHub webhook on push to main
- **Action**: Re-run governance review, diff against stored review
- **Alert**: Flag if risk profile increased
- **Priority**: LOW

---

## Phase 3 — Developer Platform

### 3.1 Usage Analytics & Cost Tracking ⏳
- Track which teams call which agents
- Token usage and cost attribution
- Dashboard: Top consumers, most-used agents
- **Priority**: HIGH

### 3.2 Dependency Graph ⏳
- Visualize agent → tool dependencies
- Impact analysis: "What breaks if this agent goes down?"
- Interactive network diagram
- **Priority**: MEDIUM

### 3.3 CI/CD Integration ⏳
- GitHub Action: auto-register on merge to main
- Template action YAML shipped with marketplace
- Prevents registration drift
- **Priority**: MEDIUM

### 3.4 API Spec Storage ⏳
- Store OpenAPI/AsyncAPI specs
- Auto-generate "Try It Live" from spec
- Spec diff on update → changelog
- **Priority**: LOW

### 3.5 Environment Promotion ⏳
- Model: `dev → staging → prod` promotion
- Enforce governance in staging before prod
- **Priority**: LOW

---

## Phase 4 — Intelligence Layer

### 4.1 Continuous AI Monitoring ⏳
- Re-run governance review weekly against latest code
- Flag if risk profile increased
- **Priority**: MEDIUM

### 4.2 Runtime Behaviour Analysis ⏳
- Log all proxied calls
- Anomaly detection (usage spikes, PII in non-PII tools)
- Real-time security alerts
- **Priority**: HIGH

### 4.3 CVE Monitoring ⏳
- Parse dependencies from source repos
- Alert on known vulnerabilities
- Auto-create issues in source repo
- **Priority**: MEDIUM

### 4.4 Regulatory Intelligence ⏳
- Track regulatory changes (PCI-DSS updates, GDPR amendments)
- Auto-flag affected agents
- **Priority**: LOW

---

## Quick Wins (Do Next)

| What | Why | Effort | Priority |
|------|-----|--------|----------|
| Real health check polling | Dashboard becomes meaningful | Low | HIGH |
| Slack/email notifications | Reduces manual queue checking | Low | HIGH |
| Compliance expiry tracking | Immediate compliance value | Low | HIGH |
| Usage analytics dashboard | Shows ROI, prevents duplicates | Medium | HIGH |
| Enhanced review queue UI | Better UX for admins | Medium | MEDIUM |
| GitHub webhook integration | Auto-triggers re-review | Medium | MEDIUM |

---

## Non-Goals (Explicit Descoping)

- **Agent execution**: Marketplace governs agents; does not run them
- **Billing/payments**: Reports usage; Finance handles billing
- **Model serving**: Catalogues agents; does not host models
- **Cross-cloud federation**: Single-cloud (GCP) for now


