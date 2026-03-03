# Deployment Checklist

Use this checklist when deploying agent-marketplace to a new machine.

## Pre-Deployment

- [ ] Python 3.8+ installed
- [ ] Git installed (if using git deployment method)
- [ ] GCP account with Vertex AI enabled
- [ ] GCP service account key downloaded

## Server Dependencies

### MCP Server (Model Context Protocol)
- [ ] MCP server code available
- [ ] MCP server dependencies installed (`pip install -r requirements.txt`)
- [ ] MCP server running on port 8000
- [ ] Test: `curl http://localhost:8000/health` returns 200

### A2A Server (Agent-to-Agent)
- [ ] A2A server code available
- [ ] A2A server dependencies installed (`pip install -r requirements.txt`)
- [ ] A2A server running on port 9000
- [ ] Test: `curl http://localhost:9000/agents` returns agent list

## Marketplace Setup

- [ ] Agent-marketplace code transferred to target machine
- [ ] Dependencies installed: `pip install -r requirements.txt`
- [ ] `.env` file created from `.env.example`
- [ ] `.env` configured with:
  - [ ] `GCP_PROJECT_ID`
  - [ ] `GCP_LOCATION`
  - [ ] `MARKETPLACE_ADMIN_KEY` (generate with: `python -c "import secrets; print(secrets.token_urlsafe(32))"`)
  - [ ] `MARKETPLACE_DEV_KEY`
  - [ ] `MARKETPLACE_VIEWER_KEY`
  - [ ] `ALLOW_UNAUTHENTICATED_READ=true` (optional)
- [ ] GCP credentials configured:
  - [ ] Service account key file copied to target machine
  - [ ] `GOOGLE_APPLICATION_CREDENTIALS` environment variable set
  - [ ] Test: `gcloud auth application-default print-access-token` works

## Database

- [ ] If migrating: Run `python migrate_to_sqlite.py`
- [ ] If fresh install: Database will auto-create on first run

## Startup

- [ ] Start MCP server: `cd mcp-server && python server.py`
- [ ] Start A2A server: `cd a2a-server && python server.py`
- [ ] Start marketplace: `cd agent-marketplace && python app.py`
- [ ] Access UI: http://localhost:8500
- [ ] Verify stats bar shows:
  - [ ] MCP Server: ● Online
  - [ ] A2A Server: ● Online
  - [ ] Agents count > 0 (if agents registered)

## Post-Deployment Testing

- [ ] Register a test agent via API
- [ ] Verify AI governance review runs
- [ ] Check agent appears in review queue
- [ ] Approve agent as admin
- [ ] Verify agent visible to non-admin users

## Troubleshooting

If marketplace shows "MCP Server: ○ Offline":
1. Check MCP server is running: `curl http://localhost:8000/health`
2. Check firewall/port 8000 not blocked
3. Check MCP server logs for errors

If marketplace shows "A2A Server: ○ Offline":
1. Check A2A server is running: `curl http://localhost:9000/agents`
2. Check firewall/port 9000 not blocked
3. Check A2A server logs for errors

If no agents appear:
1. Register an agent with A2A server first
2. Wait 60 seconds for marketplace auto-detection
3. Check marketplace logs for governance scan activity

If 401 Unauthorized errors:
1. Set `ALLOW_UNAUTHENTICATED_READ=true` in .env
2. Or provide `X-API-Key` header in requests
3. Restart marketplace after .env changes
