# Credit Decision Agent

AI-powered credit decisioning agent for consumer lending.

## What it does

- Evaluates credit applications using GPT-4
- Pulls credit reports by SSN
- Auto-declines high-risk applicants
- Calculates risk scores using applicant data and zip code analysis

## Quick Start

```bash
pip install -r requirements.txt
python agent.py
# → http://localhost:8201
```

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/tools/evaluate_credit` | POST | Full credit evaluation with AI |
| `/tools/pull_credit_report` | POST | Pull credit report by SSN |
| `/tools/auto_decline` | POST | Auto-decline an application |
| `/receive` | POST | A2A message receiver |

## Registration

On startup, the agent self-registers with:
- A2A Server (localhost:9000)
- Agent Marketplace (localhost:8500)

## ⚠️ Demo Notice

This agent is intentionally built with governance violations for
demonstration purposes. It is designed to trigger the Agent Marketplace's
25-point governance review. **Do not use as a template for production agents.**
