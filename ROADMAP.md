# Agent Marketplace — Product Roadmap

## Current State (v1.0)

**Completed:**
- ✅ Aggregates agents from A2A server and tools from MCP server
- ✅ SQLite database with audit logging
- ✅ Approval workflow (pending_review → under_review → approved/rejected)
- ✅ Authentication & RBAC (API key-based: viewer, developer, admin)
- ✅ AI governance review with 25 comprehensive checks (15 security + 10 AI governance)
- ✅ Framework-aware patterns loaded from YAML (9 frameworks, 47 risk patterns)
- ✅ Background scanner auto-detects agents from A2A registry
- ✅ Live-unreviewed status for auto-detected agents (not blocked, but flagged)
- ✅ Real source code fetching from GitHub (multi-file, scored ranking)
- ✅ Enforcement layer (403 for unapproved agents via proxy/invoke)
- ✅ SSRF protection on proxy endpoint
- ✅ Unverified compliance claim detection (strikethrough badges)
- ✅ Duplicate detection
- ✅ Demo agents (credit-decision-agent + kyc-verification-agent)
- ✅ Startup/stop scripts

---

## Phase 1 — Operational Gaps (Week 1 priorities)

These are things someone will ask about in the first week of internal use.

### 1.1 Agent Deregistration
- **Problem**: No way to remove an agent. Sunset agents stay in the catalog forever.
- **Solution**: `DELETE /api/agents/{agent_id}` endpoint + "Deregister" button in detail panel. Sets status to `deregistered`, removes from A2A registry. Keeps audit trail.
- **Priority**: HIGH
- **Effort**: Small

### 1.2 Re-trigger Governance Review
- **Problem**: If a team fixes issues flagged by the AI review, there's no way to re-scan. They'd have to delete the DB entry and re-register.
- **Solution**: "Re-scan" button in detail panel → calls governance agent with fresh source code fetch. Appends new review to history (doesn't overwrite).
- **Priority**: HIGH
- **Effort**: Small

### 1.3 Agent Versioning
- **Problem**: Re-registering an agent overwrites the previous record. No history of "v1 was rejected, v2 was approved."
- **Solution**: Add `version` field to agents table. Each registration creates a new version. UI shows version history with diff between reviews.
- **Priority**: HIGH
- **Effort**: Medium

### 1.4 Tool Governance for Auto-Detected Tools
- **Problem**: Background scanner only scans agents from A2A. MCP tools get `active` status with no governance review. They bypass everything.
- **Solution**: Extend background scanner to also scan MCP tools. Apply same `live_unreviewed` → AI review → `live_reviewed`/`under_review` flow.
- **Priority**: HIGH
- **Effort**: Small

### 1.5 Fix Status Filter
- **Problem**: Status filter dropdown has `active`, `under-review`, `deprecated` but not the actual statuses used: `live_unreviewed`, `live_reviewed`, `approved`, `rejected`, `pending_review`, `under_review`.
- **Solution**: Update filter dropdown to match real statuses. Add "Needs Attention" meta-filter.
- **Priority**: MEDIUM
- **Effort**: Small

---

## Phase 2 — Operational Maturity (Week 2-4)

### 2.1 Notifications (Slack/Email)
- **Problem**: Nobody will check the review queue manually. Governance that requires manual checking gets ignored.
- **Solution**: Webhook integration. Fire on: new agent detected, review completed with issues, agent approved/rejected, compliance expiring.
- **Config**: `WEBHOOK_URL` in .env, simple POST with JSON payload.
- **Priority**: HIGH
- **Effort**: Medium

### 2.2 Bulk Approve/Reject
- **Problem**: If 10 agents get auto-detected at once, approving them one by one is painful.
- **Solution**: Checkbox selection on cards + "Approve Selected" / "Reject Selected" buttons. Batch API endpoint.
- **Priority**: MEDIUM
- **Effort**: Medium

### 2.3 Export & Compliance Reporting
- **Problem**: Compliance officers will ask "give me a report of all agents and their governance status."
- **Solution**: `GET /api/export?format=csv` and `GET /api/export?format=pdf`. Include agent details, governance review summary, risk flags, approval status, audit trail.
- **Priority**: HIGH
- **Effort**: Medium

### 2.4 Real Health Monitoring
- **Problem**: Health percentage in header is based on status field, not actual liveness. Nobody pings agent endpoints.
- **Solution**: Background task pings every registered endpoint every 60s. States: `healthy` → `degraded` (1 failure) → `down` (3 consecutive). Show in UI with last-checked timestamp.
- **Priority**: MEDIUM
- **Effort**: Medium

### 2.5 Per-User Identity
- **Problem**: Audit log shows "demo-user" for everything because auth is in demo mode.
- **Solution**: Disable demo mode bypass. Distribute real API keys to teams. Audit log shows actual user/team identity.
- **Priority**: HIGH
- **Effort**: Small (code exists, just needs config change + key distribution)

---

## Phase 3 — Platform Features (Month 2+)

### 3.1 Compliance Expiry Tracking
- **Problem**: PCI-DSS attestations expire annually. No tracking, no warnings.
- **Add fields**: `compliance_reviewed_at`, `compliance_expires_at`, `compliance_evidence_url`
- **Logic**: Surface "Expiring in 30 days" warnings in UI. Include in notifications.
- **Priority**: HIGH
- **Effort**: Small

### 3.2 Agent Dependency Graph
- **Problem**: No visibility into agent-to-agent or agent-to-tool call chains. "What breaks if this agent goes down?" is unanswerable.
- **Solution**: Track `calls_other_agents` from governance review. Build dependency graph. Interactive network diagram in UI. Impact analysis on deregistration.
- **Priority**: MEDIUM
- **Effort**: Medium

### 3.3 CI/CD Integration
- **Problem**: Teams register agents manually through UI or API. Registration drifts from actual deployments.
- **Solution**: GitHub Action template that auto-registers on merge to main. Prevents registration drift. Template shipped with marketplace.
- **Priority**: MEDIUM
- **Effort**: Medium

### 3.4 Continuous Re-Review
- **Problem**: Governance review is a point-in-time snapshot. Code changes after initial review aren't detected.
- **Solution**: GitHub webhook on push to main → re-run governance review → diff against stored review → alert if risk profile increased.
- **Priority**: MEDIUM
- **Effort**: Medium

### 3.5 GitLab/Bitbucket/CodeCommit Support
- **Problem**: Source code fetching only works for GitHub. Enterprise teams on other platforms get metadata-only reviews (no source analysis).
- **Solution**: Add provider detection in `fetch_source_code()`. GitLab API, Bitbucket API, CodeCommit via boto3. Same file scoring/ranking logic.
- **Priority**: HIGH (if any team uses non-GitHub)
- **Effort**: Medium

---

## Phase 4 — Intelligence Layer (Month 3+)

### 4.1 Usage Analytics & Cost Tracking
- Track which teams call which agents
- Token usage and cost attribution per team
- Dashboard: top consumers, most-used agents, cost trends
- **Priority**: HIGH
- **Effort**: Large

### 4.2 Runtime Behavior Monitoring
- Log all proxied calls
- Anomaly detection (usage spikes, PII in non-PII tools)
- Real-time security alerts
- **Priority**: HIGH
- **Effort**: Large

### 4.3 CVE Monitoring
- Parse dependencies from source repos
- Alert on known vulnerabilities (cross-reference with NVD/OSV)
- Auto-create issues in source repo
- **Priority**: MEDIUM
- **Effort**: Medium

### 4.4 Custom Governance Policies
- Let orgs define their own checks beyond the 25
- Policy-as-code: YAML/JSON rules that the LLM evaluates against
- Team-specific policies (e.g., "Risk team agents must have PCI-Scoped tag")
- **Priority**: MEDIUM
- **Effort**: Large

### 4.5 Multi-Tenant / Team Isolation
- Teams own agents; visibility controls (public, team-only, admin-only)
- `Internal-Only` agents only visible to owner team + admins
- Team-scoped API keys
- **Priority**: MEDIUM
- **Effort**: Medium

### 4.6 Environment Promotion
- Model: `dev → staging → prod` promotion
- Enforce governance in staging before prod
- Different approval requirements per environment
- **Priority**: LOW
- **Effort**: Large

---

## Quick Wins (Do Next)

| What | Why | Effort | Priority |
|------|-----|--------|----------|
| Agent deregistration | Can't remove sunset agents | Small | HIGH |
| Re-scan button | Teams can't fix and re-verify | Small | HIGH |
| Tool governance scanner | MCP tools bypass all checks | Small | HIGH |
| Fix status filter dropdown | Can't filter by real statuses | Small | MEDIUM |
| Slack notifications | Nobody checks queue manually | Medium | HIGH |
| Enable real auth | Audit trail is meaningless without it | Small | HIGH |
| Compliance expiry fields | Immediate compliance value | Small | HIGH |

---

## Non-Goals (Explicit Descoping)

- **Agent execution**: Marketplace governs agents; does not run them
- **Billing/payments**: Reports usage; Finance handles billing
- **Model serving**: Catalogues agents; does not host models
- **Cross-cloud federation**: Single-cloud (GCP) for now
- **Custom LLM hosting**: Uses Vertex AI; does not manage model deployments
