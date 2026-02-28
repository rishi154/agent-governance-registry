# Agent Marketplace — Live Demo Guide

**Audience**: Leadership / decision-makers
**Duration**: 15–20 minutes
**Goal**: Approval for a governed AI Agent Marketplace across the organisation

---

## Before You Enter the Room

Run this once. It resets everything to the clean starting state.

```bash
# Terminal 1 — A2A server (keep running)
cd c:/work/projects/ap2_a2a_server
python main.py

# Terminal 2 — Marketplace (keep running)
cd c:/work/projects/agent-marketplace
python app.py

# Terminal 3 — Reset to demo baseline (run once, then keep open for registrations)
cd c:/work/projects/agent-marketplace
python scripts/demo_start.py
```

You should see: **✅ READY TO DEMO!**

Open browser to **http://localhost:8500** — keep it on the Agents tab.

---

## The Narrative

> "We have dozens of teams independently building AI agents during our Agentic AI POC.
> Without a marketplace, every team reinvents the wheel, no one knows what exists,
> and — critically — we have no visibility into what data these agents are touching.
> This is the governance layer that changes that."

---

## Demo Steps

---

### Step 1 — Show the Starting State (2 min)

**What they see**: 1 agent (Fraud Detection), 4 tools. Clean, real.

> "The Risk & Fraud team registered their fraud scoring agent three months ago.
> It went through an AI governance review when it registered — let me show you what that looks like."

**Click on `Fraud Detection Agent`** → detail panel opens

Point out:
- **Owner**: Risk & Fraud
- **Compliance badges**: PCI-Scoped ✓, Production-Ready ✓
- **AI Review section**: Confidence: HIGH, PCI Scope: CONFIRMED
  - "The AI independently verified these compliance claims — it wasn't just trusting what the team said."
  - "It caught one risk: the velocity check accepts a raw card ID. It recommended tokenisation."
- **Auth Assessment**: "API key enforced on all endpoints — the AI checked this in the code."

> "This is what a healthy, reviewed agent looks like. Now let me show what happens
> when a different team tries to register something without proper controls."

---

### Step 2 — Duplicate Detection in the Registration Form (2 min)

Click **Register New** (top right)

In the form:
- Type `fraud risk scoring` in the **Description** field
- Pause for 1 second

> "Watch what happens as I describe what I want to build..."

**The similarity warning fires automatically.**

Point out:
- "The system flagged that `fraud_detection_agent` already covers this with a 71% keyword match."
- "Before I write a single line of code, I know this already exists and I know who owns it."
- "This is how we prevent the same tool being built four times by four different teams."

**Close the form** (don't submit).

---

### Step 3 — Register a Risky Agent (Live AI Review) (5 min)

> "Now let's watch what happens when a team registers something genuinely problematic."

Switch to **Terminal 3** (keep browser visible if you have two screens).

```bash
python scripts/register_agent.py --agent-only
```

The script registers three agents one after another. Focus on **card_authorization_agent** first.

**While it's processing** (10–20s):
> "The AI governance agent is now reading the registration — the description,
> the capabilities, the claimed compliance tags — and cross-checking them independently."

**When the output appears**, walk through it:

```
Registration status: updated
PCI Scope: CONFIRMED   PII Scope: NONE   Requires Human Review: YES

Risk Flags:
  🔴 get_raw_pan capability exposes raw Primary Account Numbers — no masking mentioned
  🔴 auth_required is False — this PCI-scoped agent has no authentication
  🔴 Returns raw PAN in API response for downstream processing

Unverified Claims:
  🟡 PCI-Scoped — claimed but no masking or tokenisation controls evidenced
  🟡 Production-Ready — auth disabled contradicts production readiness
```

> "The team told us this was PCI-compliant and production-ready.
> The AI found they handle raw card numbers, return them unmasked in API responses,
> and have authentication turned off. It flagged all three as unverified claims."

> "Requires Human Review: YES — this would go into an approval queue.
> It does NOT go live until a human signs off."

Now switch to **browser** and refresh or navigate to Agents tab.
Click on **Card Authorization Agent** → show the AI review badges in red.

---

### Step 4 — Register a Clean Agent (Contrast) (2 min)

The script also registered `settlement_report_agent`. Find it in the output.

Point out:
- No PCI scope (aggregated totals only, no card data)
- No risk flags — or only minor ones
- Requires Human Review: NO — this could auto-approve

> "Compare: the settlement agent handles aggregated financial totals, no card data.
> The AI cleared it. The card auth agent — same registration process — got flagged immediately."

> "This is governance that scales. You don't need a human to read every registration."

---

### Step 5 — Discovery and Filtering (2 min)

Back in the browser:

**Search bar**: Type `fraud` → only fraud-related items appear
> "Any team looking to build fraud tooling finds the existing agent immediately."

**Filter by Team**: Select `Risk & Fraud`
> "Teams can see everything their team owns and what other teams depend on."

**Filter by Compliance**: Select `PCI-Scoped`
> "Security can instantly see every agent touching card data across the whole organisation."

---

### Step 6 — Try It Live (2 min)

Click on **Score Transaction** tool → `Try It Live` section

The example request is pre-filled:
```json
{
  "transaction_id": "TXN-20260228-001",
  "amount": 7500.00,
  "merchant_id": "MHIGH-NYC-042",
  "card_country": "US",
  "merchant_country": "MX"
}
```

Headers: `X-API-Key: demo-key-12345` (pre-filled)

Click **Send** → live response appears:
```json
{
  "risk_score": 75,
  "recommendation": "decline",
  "signals": { "high_amount": true, "cross_border": true, "high_risk_merchant": true }
}
```

> "A developer from any team can discover this tool, understand exactly what it does,
> and test it against real data — without needing to call the Risk & Fraud team."

---

### Closing (1 min)

> "Three things this gives us today:"

1. **Visibility** — leadership and teams can see every AI agent and tool in the organisation,
   who owns it, and what data it touches.

2. **Governance** — an AI independently reviews every registration for PCI/PII risks,
   compliance claims, and duplicate effort — before anything goes live.

3. **Reuse** — teams discover what already exists before building.
   We estimate 30–40% of current POC work is duplicated across teams.

> "The alternative is what we have today: agents proliferating across teams,
> no one knowing what data they access, compliance attestations that are self-reported
> and unverified, and leadership with zero visibility."

---

## If They Ask...

**"Can this work with Google ADK / other frameworks?"**
> "Yes — any agent with an HTTP endpoint can register. We've documented LangChain, CrewAI,
> AutoGen, and AWS Bedrock. See `INTEROPERABILITY.md`."

**"What stops someone from bypassing this?"**
> "Good challenge — the next milestone is an approval workflow where items flagged
> 'Requires Human Review' go into a queue and cannot go live without a named approver.
> Currently governance is enforced at registration; the queue makes it enforced at deployment."

**"Where is this running?"**
> "This is a local demo. Production deployment would run in GCP behind our internal network,
> with SSO auth on the marketplace itself."

**"Who maintains the AI governance rules?"**
> "The system prompt in the governance agent defines what to look for — PCI/PII signals,
> auth enforcement, compliance claim verification. It's versioned in the source repo
> and can be updated as our policies evolve."

---

## Reset Mid-Demo (if something goes wrong)

```bash
# In Terminal 3:
python scripts/demo_start.py

# Then refresh the browser
```

This restores the clean baseline in under 5 seconds.
