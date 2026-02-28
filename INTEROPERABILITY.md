# Agent Marketplace — Framework Interoperability

## How the Marketplace Connects to Agents

The marketplace does **not** care what technology built your agent. It communicates via two standard interfaces:

1. **Registration** — a one-time `POST /api/register/agent` with metadata (ID, endpoint URL, capabilities)
2. **Invocation** — HTTP POST to the agent's registered `endpoint` URL

As long as your agent has an HTTP endpoint and can accept a JSON payload, it can be registered.

---

## The A2A Protocol

This marketplace uses the **Agent-to-Agent (A2A)** open protocol — originally developed by Google with contributions from Anthropic and others. A2A is framework-agnostic: it defines how agents identify themselves (via DIDs) and exchange messages, not how agents are built.

**Minimum A2A contract your agent must implement:**

```http
POST /receive
Content-Type: application/json

{
  "from_did": "did:key:z6Mk...",
  "to_did":   "did:key:z6Mk...",
  "message_type": "your_capability_name",
  "body": { ...capability-specific payload... },
  "signature": "demo-sig"
}
```

The response is whatever JSON your agent returns for that capability.

---

## Framework-by-Framework Guide

### Google ADK (Agent Development Kit)

**Compatibility: Full ✅**

Google ADK is the best-supported external framework because A2A originated from Google.

ADK agents expose HTTP endpoints natively. Registration is straightforward:

```python
import httpx

httpx.post("http://localhost:8500/api/register/agent", json={
    "agent_id": "my_adk_agent",
    "agent_type": "conversational",
    "endpoint": "http://localhost:8200/receive",   # your ADK agent's URL
    "capabilities": ["answer_questions", "summarise"],
    "owner_team": "My Team",
    "compliance": [],
    "source_repo": "https://github.com/my-org/my-adk-agent",
    "description": "An agent built with Google ADK that ...",
})
```

Add a `/receive` handler to your ADK agent that maps `message_type` to your agent's tasks:

```python
from fastapi import FastAPI
from google.adk.agents import Agent  # your ADK agent

app = FastAPI()
agent = Agent(...)

@app.post("/receive")
async def receive(message: dict):
    result = await agent.run(message["body"].get("query", ""))
    return {"result": result}
```

**Vertex AI Agent Engine** (cloud-hosted ADK): The agent runs in Google's cloud without a direct HTTP endpoint you control. Options:
- Deploy a thin Cloud Run proxy that forwards marketplace messages to the Agent Engine session API
- Register the proxy URL as the `endpoint` in the marketplace

---

### LangChain / LangGraph

**Compatibility: Full ✅ (with HTTP wrapper)**

LangChain agents don't expose HTTP endpoints by default. Wrap in FastAPI:

```python
from fastapi import FastAPI
from langchain.agents import AgentExecutor

app = FastAPI()
agent_executor = AgentExecutor(...)  # your LangChain agent

@app.post("/receive")
async def receive(message: dict):
    result = agent_executor.invoke({"input": message["body"]})
    return {"output": result["output"]}
```

LangGraph agents (stateful graph-based) follow the same pattern — expose the graph's `invoke` or `astream` behind a `/receive` endpoint.

**LangServe**: If you're using LangServe, it already generates HTTP endpoints. Point the marketplace at your LangServe endpoint and add a `/receive` adapter.

---

### CrewAI

**Compatibility: Full ✅ (with HTTP wrapper)**

CrewAI crews run synchronously by default. Wrap in FastAPI with async execution:

```python
from fastapi import FastAPI
from crewai import Crew, Task, Agent
import asyncio

app = FastAPI()

@app.post("/receive")
async def receive(message: dict):
    crew = Crew(agents=[...], tasks=[Task(...)])
    result = await asyncio.get_event_loop().run_in_executor(
        None, crew.kickoff, {"input": message["body"]}
    )
    return {"result": str(result)}
```

---

### AutoGen / AG2

**Compatibility: Full ✅ (with HTTP wrapper)**

AutoGen multi-agent conversations are orchestrated in-process. Expose the entry point:

```python
from fastapi import FastAPI
import autogen

app = FastAPI()

@app.post("/receive")
async def receive(message: dict):
    assistant = autogen.AssistantAgent("assistant", ...)
    user_proxy = autogen.UserProxyAgent("user", ...)
    user_proxy.initiate_chat(assistant, message=str(message["body"]))
    # Extract last assistant message as result
    last = user_proxy.chat_messages[assistant][-1]["content"]
    return {"result": last}
```

---

### AWS Bedrock Agents

**Compatibility: Partial ⚠️**

Bedrock Agents run in AWS — no direct HTTP endpoint you control. Two approaches:

**Option A — Lambda proxy** (recommended):
Deploy an AWS Lambda + API Gateway that receives marketplace A2A messages and forwards them to Bedrock's `invoke_agent` API:

```python
# lambda_handler.py
import boto3

bedrock = boto3.client("bedrock-agent-runtime")

def handler(event, context):
    body = event["body"]
    response = bedrock.invoke_agent(
        agentId="YOUR_AGENT_ID",
        agentAliasId="TSTALIASID",
        sessionId="marketplace-session",
        inputText=str(body)
    )
    result = "".join(c["chunk"]["bytes"].decode() for c in response["completion"])
    return {"statusCode": 200, "body": result}
```

Register the API Gateway URL as the `endpoint` in the marketplace.

**Option B — Wrapper service**: Deploy a small FastAPI service in AWS that wraps Bedrock Agents. Same concept as the Lambda proxy but as a persistent service.

**Limitation**: Bedrock Agent sessions are stateful. The marketplace's stateless A2A messages don't map cleanly to Bedrock's session model. You'll need to manage session IDs on the proxy side.

---

### OpenAI Assistants API

**Compatibility: Metadata only ⚠️**

OpenAI Assistants use a polling/run model — there's no persistent HTTP endpoint. A synchronous `/receive` endpoint is not natural here.

Approach — blocking proxy:

```python
from openai import OpenAI
from fastapi import FastAPI

app = FastAPI()
client = OpenAI()

@app.post("/receive")
async def receive(message: dict):
    thread = client.beta.threads.create()
    client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=str(message["body"])
    )
    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread.id,
        assistant_id="asst_YOUR_ID"
    )
    msgs = client.beta.threads.messages.list(thread_id=thread.id)
    return {"result": msgs.data[0].content[0].text.value}
```

**Limitation**: Each call creates a new thread — no conversation state across marketplace invocations. Cost is also higher due to thread overhead.

---

### rsagenticai (this organisation's framework)

**Compatibility: Full ✅ — native**

rsagenticai agents already use the same Vertex AI stack. They can register directly with the marketplace. The `demo_agent/fraud_detection_agent.py` is the reference implementation.

Use `agent_template.py` in `ap2_a2a_server/` as the starting point for new agents — it handles both A2A self-registration and marketplace registration on startup.

---

## What the Marketplace Needs From Any Agent

| Field | Required | Description |
|-------|----------|-------------|
| `endpoint` | Yes | HTTP URL that accepts POST `/receive` |
| `capabilities` | Yes | List of strings naming what the agent can do |
| `source_repo` | Yes | Git repository URL (for governance review) |
| `owner_team` | Yes | Team responsible for this agent |
| `agent_id` | Yes | Unique identifier (snake_case) |
| `/receive` handler | Yes | Accepts A2A message JSON, returns result JSON |
| `/health` endpoint | Recommended | Returns `{"status": "ok"}` — used for uptime monitoring |

## What the Marketplace Does NOT Require

- Any specific AI framework or LLM provider
- Any specific programming language
- Cloud provider lock-in
- The agent to be aware of the marketplace at all — registration can be done externally

---

## Testing Interoperability

Once your agent is running with a `/receive` endpoint, test from the marketplace:

```bash
# 1. Register the agent
curl -X POST http://localhost:8500/api/register/agent \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "my_test_agent",
    "agent_type": "custom",
    "endpoint": "http://localhost:8200/receive",
    "capabilities": ["my_capability"],
    "owner_team": "My Team",
    "source_repo": "https://github.com/my-org/my-agent",
    "description": "Test agent"
  }'

# 2. Invoke via marketplace
curl -X POST http://localhost:8500/api/invoke-agent \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "my_test_agent",
    "capability": "my_capability",
    "payload": {"query": "hello"}
  }'
```
