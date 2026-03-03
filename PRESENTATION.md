# AI Agent Marketplace - Presentation Pitch

---

## The Problem

**Organizations are building AI agents everywhere** - different teams, different frameworks, no central visibility.

**Critical gaps:**
- ❌ No one knows what agents exist or what they do
- ❌ Agents handle PII/PCI data without oversight
- ❌ No approval process before production deployment
- ❌ Security vulnerabilities go undetected
- ❌ Duplicate agents waste resources
- ❌ Compliance teams can't audit agent behavior

**Result:** Shadow AI sprawl with massive security and compliance risk.

---

## The Solution: AI Agent Marketplace

**A lightweight governance platform that provides:**

✅ **Centralized Discovery** - Single catalog of all agents across your organization  
✅ **Automated Security Scanning** - AI-powered review of every agent (15 governance checks)  
✅ **Approval Workflow** - Human-in-the-loop before production deployment  
✅ **Compliance Tracking** - PCI/PII scope detection, audit trails  
✅ **Framework-Agnostic** - Works with LangChain, CrewAI, AutoGen, custom agents  

---

## How It Works

### 3-Step Process:

**1. Register Agent** (via UI or API)
```python
POST /api/agents
{
  "agent_id": "fraud_detector",
  "source_repo": "github.com/org/fraud-agent",
  "owner_team": "Risk & Fraud"
}
```

**2. AI Governance Review** (automatic, 3-5 seconds)
- Analyzes source code from GitHub
- Detects PII/PCI handling
- Identifies security risks
- Validates compliance claims
- Generates recommendations

**3. Human Approval** (admin reviews findings)
- ✓ Approve → Agent goes live
- ✗ Reject → Agent blocked from production

---

## Live Demo

**Show:**
1. **Dashboard** - 3 agents, governance status
2. **Card Authorization Agent** - Click to open
3. **AI Review Results**:
   - 🔴 7 Risk Flags detected
   - "Logs full card numbers to audit log"
   - "Returns raw PAN in API response"
   - "Auth disabled for payment processing"
4. **Approve/Reject Buttons** - Admin decision point
5. **Audit Trail** - Who approved what, when

---

## Key Differentiators

### vs. Existing Solutions (LangSmith, DataRobot, etc.)

| Feature | Marketplace | Others |
|---------|-------------|--------|
| **Pre-deployment governance** | ✅ | ❌ (post-deployment only) |
| **Multi-agent discovery** | ✅ | ❌ (single model focus) |
| **Approval workflow** | ✅ | ❌ |
| **Setup time** | Minutes | Weeks/Months |
| **Cost** | $0.006/agent | $39-299/month |
| **Framework-agnostic** | ✅ | ❌ (vendor lock-in) |

---

## AI Governance Checks (15 Total)

**Security:**
- Secrets & credentials detection
- Prompt injection risks
- Authentication assessment
- Input validation

**Compliance:**
- PII scope (SSN, emails, phone numbers)
- PCI-DSS scope (payment card data)
- Data retention & GDPR
- Unverified compliance claims

**Operations:**
- Cost & token tracking
- Rate limiting & DoS protection
- Dependency vulnerabilities
- Observability & monitoring

---

## Real-World Impact

**Scenario: Card Authorization Agent**

**Without Marketplace:**
- Agent deployed to production
- Logs raw credit card numbers
- PCI audit finds violation
- $50K-500K fine + remediation costs

**With Marketplace:**
- AI detects issue in 5 seconds
- Admin rejects deployment
- Team fixes before production
- **Zero compliance risk**

---

## Architecture

```
┌─────────────────────────────────────┐
│  Agent Marketplace (port 8500)      │
│  - Governance & approval            │
│  - Centralized catalog              │
└─────────────────────────────────────┘
         │              │
         ▼              ▼
┌──────────────┐  ┌──────────────┐
│  A2A Server  │  │  Vertex AI   │
│  (agents)    │  │  (reviews)   │
└──────────────┘  └──────────────┘
```

**Key Feature:** Auto-detects agents registered directly with A2A server  
→ **No bypass possible** - all agents get reviewed within 60 seconds

---

## Deployment

**Requirements:**
- Python 3.8+
- GCP account (Vertex AI)
- A2A server running

**Setup:**
```bash
pip install -r requirements.txt
cp .env.example .env
# Configure GCP credentials
python app.py
```

**Cost:** ~$0.006 per agent review (~2000 tokens)

---

## Roadmap

**Phase 1 (Complete):**
- ✅ Automated governance (15 checks)
- ✅ Approval workflow
- ✅ SQLite storage + audit logs
- ✅ Authentication & RBAC

**Phase 2 (Next):**
- Real-time monitoring dashboard
- Slack/email notifications
- Advanced analytics (cost tracking, usage patterns)
- Integration with CI/CD pipelines

**Phase 3 (Future):**
- Multi-tenant support
- Custom governance policies
- Agent versioning & rollback
- Compliance report generation

---

## Call to Action

**Try it now:**
```bash
git clone <repo-url>
cd agent-marketplace
./deploy.sh
```

**Access UI:** http://localhost:8500

---

## Backup Slides

### Technical Details
- **Database:** SQLite (scales to 1000+ agents)
- **AI Model:** Gemini 2.5 Flash Lite (upgradeable to Claude Opus)
- **Auth:** API key-based (3 roles: viewer, developer, admin)
- **Review Time:** 3-5 seconds per agent
- **Background Scanner:** Runs every 60 seconds

### Security
- All governance reviews logged with actor tracking
- Audit trail for every approval/rejection
- API key rotation supported
- Optional unauthenticated read mode for internal tools

### Market Gap
Most existing solutions focus on:
- ✅ Model performance monitoring (accuracy, drift)
- ✅ Bias/fairness for ML models
- ✅ Explainability for predictions

But they **lack**:
- ❌ Multi-agent system governance
- ❌ Agent registration & discovery
- ❌ Pre-deployment security scanning
- ❌ Lightweight approval workflows

**We fill this gap.**
