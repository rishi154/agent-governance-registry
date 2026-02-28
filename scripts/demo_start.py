#!/usr/bin/env python3
"""
demo_start.py — Run this BEFORE entering the room.

What it does:
  1. Checks the marketplace is running
  2. Checks the A2A server registry state (warns if stale agents present)
  3. Resets enrichments.json to the clean demo baseline (1 agent + 4 tools)
  4. Seeds the baseline fraud_detection_agent to the A2A registry
  5. Verifies the governance AI is configured
  6. Prints the demo URL and a go/no-go summary

Usage:
    python scripts/demo_start.py
    python scripts/demo_start.py --url http://localhost:8500
    python scripts/demo_start.py --skip-a2a-check   # if A2A has leftover agents and that's OK
"""

import sys
import argparse
from pathlib import Path

try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)

RESET  = "\033[0m"
BOLD   = "\033[1m"
RED    = "\033[91m"
YELLOW = "\033[93m"
GREEN  = "\033[92m"
CYAN   = "\033[96m"
DIM    = "\033[2m"

def c(text, code): return f"{code}{text}{RESET}"

BASELINE_AGENT = {
    "agent_id": "fraud_detection_agent",
    "agent_type": "risk",
    "endpoint": "http://localhost:8101/receive",
    "did": "did:key:z6MkFraudDetectXYZ001",
    "public_key": "demo-public-key-fraud",
    "capabilities": ["score_transaction", "velocity_check", "merchant_risk_lookup"],
}


def step(n, text): print(f"\n  {c(f'Step {n}', BOLD)}: {text}")
def ok(text):       print(f"    {c('✅', GREEN)} {text}")
def warn(text):     print(f"    {c('⚠', YELLOW)}  {text}")
def fail(text):     print(f"    {c('✗', RED)}  {text}")
def info(text):     print(f"    {c('→', DIM)} {text}")


def main():
    parser = argparse.ArgumentParser(description="Prepare the marketplace for a live demo.")
    parser.add_argument("--url", default="http://localhost:8500")
    parser.add_argument("--a2a-url", default="http://localhost:9000")
    parser.add_argument("--skip-a2a-check", action="store_true",
                        help="Don't warn about leftover agents in A2A registry")
    args = parser.parse_args()

    print(f"\n{c('═' * 60, CYAN)}")
    print(c("  AGENT MARKETPLACE — DEMO RESET", BOLD))
    print(c('═' * 60, CYAN))
    print(f"  Marketplace : {args.url}")
    print(f"  A2A server  : {args.a2a_url}")

    issues = []

    # ── Step 1: Marketplace reachable ─────────────────────────────────────
    step(1, "Check marketplace is running")
    try:
        r = httpx.get(f"{args.url}/api/stats", timeout=4.0)
        r.raise_for_status()
        stats = r.json()
        ok(f"Marketplace is UP  (agents={stats.get('total_agents')}, tools={stats.get('total_tools')})")
    except httpx.ConnectError:
        fail(f"Marketplace not reachable at {args.url}")
        info("Start it:  cd c:/work/projects/agent-marketplace && python app.py")
        issues.append("Marketplace not running")
    except Exception as e:
        warn(f"Marketplace responded with error: {e}")

    # ── Step 2: A2A server registry ────────────────────────────────────────
    step(2, "Check A2A agent registry")
    a2a_ok = False
    try:
        r = httpx.get(f"{args.a2a_url}/agents", timeout=4.0)
        agents = r.json().get("agents", [])
        existing_ids = [a["agent_id"] for a in agents]
        baseline_ids = [BASELINE_AGENT["agent_id"]]
        extra = [aid for aid in existing_ids if aid not in baseline_ids]

        if not existing_ids:
            ok("A2A registry is empty — perfect clean state")
            a2a_ok = True
        elif extra and not args.skip_a2a_check:
            warn(f"A2A has {len(existing_ids)} agent(s) already registered:")
            for aid in existing_ids:
                print(f"       {'(baseline)' if aid in baseline_ids else '(leftover)'} {aid}")
            info("For a fully clean demo: restart the A2A server, then re-run this script.")
            info("Or pass --skip-a2a-check to proceed anyway (leftover agents will appear in UI).")
        else:
            ok(f"A2A has {len(existing_ids)} agent(s) — proceeding")
            a2a_ok = True
    except httpx.ConnectError:
        fail(f"A2A server not reachable at {args.a2a_url}")
        info("Start it:  cd c:/work/projects/ap2_a2a_server && python main.py")
        issues.append("A2A server not running")
    except Exception as e:
        warn(f"A2A check failed: {e}")

    # ── Step 3: Reset enrichments to baseline ──────────────────────────────
    step(3, "Reset enrichments to demo baseline (1 agent + 4 tools)")
    try:
        r = httpx.post(f"{args.url}/api/demo/reset", timeout=5.0)
        r.raise_for_status()
        data = r.json()
        ok(f"Enrichments reset: {data.get('agents')} | tools: {data.get('tools')}")
    except httpx.ConnectError:
        fail("Cannot reach marketplace to reset — is it running?")
        issues.append("Could not reset enrichments")
    except Exception as e:
        fail(f"Reset failed: {e}")
        issues.append("Enrichment reset failed")

    # ── Step 4: Seed baseline agent to A2A ────────────────────────────────
    step(4, "Register baseline agent to A2A registry")
    try:
        r = httpx.post(f"{args.a2a_url}/agents/register", json=BASELINE_AGENT, timeout=5.0)
        if r.status_code == 400 and "already registered" in r.text:
            ok("fraud_detection_agent already in A2A registry (fine for demo)")
        elif r.status_code == 200 or r.status_code == 201:
            ok("fraud_detection_agent registered to A2A")
        else:
            warn(f"A2A returned {r.status_code}: {r.text[:100]}")
    except httpx.ConnectError:
        warn("A2A not reachable — skipping agent seed")
        info("The fraud agent will not appear in the Agents tab without A2A running")
    except Exception as e:
        warn(f"Seed failed: {e}")

    # ── Step 5: Governance AI check ────────────────────────────────────────
    step(5, "Check governance AI (Claude on Vertex AI)")
    try:
        r = httpx.get(f"{args.url}/api/governance/status", timeout=4.0)
        data = r.json()
        if data.get("ready"):
            ok(f"Governance AI ready  model={data.get('model')}  region={data.get('region')}")
        else:
            warn("Governance AI NOT configured — registrations will have no AI review")
            info(f"project: {data.get('project')}")
            info("Fix: add GCP_PROJECT_ID and GCP_LOCATION to .env, restart marketplace")
            info("Also: gcloud auth application-default login")
            issues.append("Governance AI not configured")
    except Exception as e:
        warn(f"Could not check governance: {e}")

    # ── Summary ────────────────────────────────────────────────────────────
    print(f"\n{c('═' * 60, CYAN)}")
    if issues:
        print(c("  ⚠  NOT READY — fix these before the demo:", YELLOW))
        for issue in issues:
            print(f"     • {issue}")
    else:
        print(c("  ✅  READY TO DEMO!", GREEN))
        print(f"\n  Open in browser:  {c(args.url, CYAN)}")
        print(f"\n  Starting state:")
        print(f"    • 1 agent:  fraud_detection_agent  (already AI-reviewed ✅)")
        print(f"    • 4 tools:  score_transaction, velocity_check,")
        print(f"                merchant_risk_lookup, pci_data_masking")
        print(f"\n  Demo registration commands (run in a separate terminal):")
        print(f"    {c('# Register a bad agent (expect AI flags):', DIM)}")
        print(f"    python scripts/register_agent.py --agent-only")
        print(f"    {c('# Register tools:', DIM)}")
        print(f"    python scripts/register_agent.py --tool-only")
        print(f"\n  See the full demo script:")
        print(f"    {c('scripts/DEMO_GUIDE.md', CYAN)}")
    print(c('═' * 60, CYAN))


if __name__ == "__main__":
    main()
