# AI Agent Marketplace

Lightweight governance platform for AI agent ecosystems with automated security scanning, approval workflows, and centralized agent discovery.

**📊 [View Presentation Pitch](PRESENTATION.md)** | **🚀 [Deployment Checklist](DEPLOYMENT_CHECKLIST.md)** | **🗺️ [Roadmap](ROADMAP.md)**

## Features

- **Automated AI Governance**: 25 comprehensive checks (15 security + 10 AI governance)
- **Approval Workflow**: Human-in-the-loop review with pending → under_review → approved/rejected states
- **Authentication & RBAC**: API key-based auth with 3 roles (viewer, developer, admin)
- **SQLite Storage**: Scalable database with audit logging
- **A2A Integration**: Auto-detects agents registered directly with A2A server
- **Framework-Agnostic**: Works with any agent framework (LangChain, CrewAI, AutoGen, custom)

## Quick Start

### 1. Prerequisites

- Python 3.8+
- GCP account with Vertex AI enabled
- GCP service account key with Vertex AI permissions
- **MCP Server** running (default: http://localhost:8000)
- **A2A Server** running (default: http://localhost:9000)

### 2. Installation

```bash
# Clone or copy the repository
cd agent-marketplace

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your settings
# Required:
GCP_PROJECT_ID=your-project-id
GCP_LOCATION=us-central1
VERTEX_CLAUDE_MODEL=gemini-2.5-flash-lite

# Authentication (generate secure keys)
MARKETPLACE_ADMIN_KEY=admin-key-here
MARKETPLACE_DEV_KEY=dev-key-here
MARKETPLACE_VIEWER_KEY=viewer-key-here

# Optional: Allow unauthenticated read access
ALLOW_UNAUTHENTICATED_READ=true
```

### 4. Start MCP and A2A Servers

**MCP Server** (Model Context Protocol - for tools):
```bash
# Clone and start MCP server
git clone https://github.com/your-org/mcp-server.git
cd mcp-server
pip install -r requirements.txt
python server.py  # Runs on http://localhost:8000
```

**A2A Server** (Agent-to-Agent - for agents):
```bash
# Clone and start A2A server
git clone https://github.com/your-org/a2a-server.git
cd a2a-server
pip install -r requirements.txt
python server.py  # Runs on http://localhost:9000
```

### 5. GCP Authentication

```bash
# Set path to your GCP service account key
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json

# Windows:
set GOOGLE_APPLICATION_CREDENTIALS=C:\path\to\service-account-key.json
```

### 6. Database Setup

If migrating from enrichments.json:
```bash
python migrate_to_sqlite.py
```

For fresh install, database will be created automatically on first run.

### 7. Run Marketplace

```bash
python app.py
```

Access UI at: http://localhost:8500

## API Usage

### Register Agent (Developer/Admin)
```bash
curl -X POST http://localhost:8500/api/agents \
  -H "X-API-Key: $MARKETPLACE_DEV_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-agent",
    "description": "Agent description",
    "source_repo": "https://github.com/org/repo",
    "owner_team": "team-name"
  }'
```

### Review Queue (Admin)
```bash
curl http://localhost:8500/api/review-queue \
  -H "X-API-Key: $MARKETPLACE_ADMIN_KEY"
```

### Approve Agent (Admin)
```bash
curl -X POST http://localhost:8500/api/agents/{agent_id}/approve \
  -H "X-API-Key: $MARKETPLACE_ADMIN_KEY"
```

### List Agents (Any role)
```bash
curl http://localhost:8500/api/agents \
  -H "X-API-Key: $MARKETPLACE_VIEWER_KEY"
```

## Architecture

```
System Components:
┌─────────────────────────────────────────────────────────────┐
│  Agent Marketplace (port 8500)                              │
│  - Governance & approval workflow                           │
│  - Centralized catalog UI                                   │
│  - AI-powered security scanning                             │
└─────────────────────────────────────────────────────────────┘
         │                                  │
         ├──────────────────┐               │
         ▼                  ▼               ▼
┌──────────────────┐  ┌──────────────┐  ┌──────────────┐
│  MCP Server      │  │  A2A Server  │  │  Vertex AI   │
│  (port 8000)     │  │  (port 9000) │  │  (GCP)       │
│  - Tool registry │  │  - Agent     │  │  - Governance│
│  - MCP protocol  │  │    registry  │  │    reviews   │
└──────────────────┘  └──────────────┘  └──────────────┘

Directory Structure:
agent-marketplace/
├── app.py                          # Main FastAPI application
├── src/
│   ├── clients.py                  # MCP & A2A client wrappers
│   ├── marketplace.py              # Agent aggregation logic
│   ├── governance_agent.py         # AI governance checks (15 checks)
│   ├── sqlite_store.py             # SQLite database layer
│   └── auth.py                     # Authentication & RBAC
├── static/                         # Web UI assets
├── migrate_to_sqlite.py            # Migration script
├── test_*.py                       # Test scripts
├── requirements.txt                # Python dependencies
└── .env                            # Configuration (not in git)
```

## Testing

```bash
# Test approval workflow
python test_approval_workflow.py

# Test A2A auto-detection
python test_direct_a2a_registration.py

# Test duplicate registration handling
python test_duplicate_registration.py
```

## Roles & Permissions

| Role | Permissions |
|------|-------------|
| **Viewer** | Read agents, view audit logs |
| **Developer** | Viewer + register agents |
| **Admin** | Developer + approve/reject agents, view review queue |

## Governance Checks

### Infrastructure & Security (1-15)
1. LLM/Model Usage Detection (hardcoded API keys, model references)
2. Secrets & Credentials Detection
3. PII Scope Detection (SSN, credit cards, emails, phone numbers)
4. PCI-DSS Scope Detection (payment processing)
5. Data Retention & Privacy (GDPR, data deletion)
6. Rate Limiting & DoS Protection
7. Model Output Validation (hallucination checks)
8. Agent Chaining & Infinite Loops
9. Cost & Token Tracking
10. Authentication & Authorization
11. Dependency Vulnerabilities
12. Observability & Monitoring
13. Input Validation & Sanitization
14. Prompt Injection Detection
15. Error Handling & Logging

### AI Governance (16-25)
16. Human-in-the-Loop Requirements (autonomous decisions, escalation paths)
17. Model Card & Transparency (model declaration, limitations, intended use)
18. Guardrails & Content Filtering (output safety, topic restrictions)
19. Bias & Fairness (protected class impact, proxy variables, feedback loops)
20. Explainability & Auditability (decision logging, reasoning traces)
21. Grounding & RAG Validation (source attribution, stale data)
22. Model Fallback & Degradation (fail-open vs fail-closed, circuit breakers)
23. Data Sent to Model Provider (PII/PCI in prompts, data minimization)
24. Consent & AI Disclosure (GDPR Art. 22, opt-out mechanisms)
25. Model Version Pinning (floating vs pinned versions, regression tests)

## Deployment Options

### Option 1: Direct Copy
```bash
# On source machine
cd c:\work
tar -czf agent-marketplace.tar.gz agent-marketplace/

# Transfer to target machine
scp agent-marketplace.tar.gz user@target:/path/

# On target machine
tar -xzf agent-marketplace.tar.gz
cd agent-marketplace
pip install -r requirements.txt
# Configure .env and run
```

### Option 2: Git Repository
```bash
# Initialize git (if not already)
git init
git add .
git commit -m "Initial commit"
git remote add origin <your-repo-url>
git push -u origin main

# On target machine
git clone <your-repo-url>
cd agent-marketplace
pip install -r requirements.txt
# Configure .env and run
```

### Option 3: Docker (create Dockerfile if needed)
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "app.py"]
```

## Troubleshooting

**401 Unauthorized**: Set `ALLOW_UNAUTHENTICATED_READ=true` in .env or provide X-API-Key header

**GCP Auth Error**: Ensure GOOGLE_APPLICATION_CREDENTIALS points to valid service account key

**Database Locked**: SQLite handles concurrent reads; only one writer at a time

**Port 8500 in use**: Change port in app.py or kill existing process

**MCP Server Offline**: Ensure MCP server is running on http://localhost:8000 (check with `curl http://localhost:8000/health`)

**A2A Server Offline**: Ensure A2A server is running on http://localhost:9000 (check with `curl http://localhost:9000/agents`)

**No agents showing**: Agents must be registered with A2A server first. Marketplace auto-detects them within 60 seconds

## Cost

- AI governance review: ~$0.006 per agent (~2000 tokens)
- Background scanner: Runs every 60s, only reviews new agents
- Storage: SQLite file grows ~1KB per agent

## License

MIT
