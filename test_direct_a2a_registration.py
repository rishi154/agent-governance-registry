#!/usr/bin/env python3
"""
Test script: Register an agent directly with A2A server (bypassing marketplace).
This simulates the governance bypass scenario.

Run: python test_direct_a2a_registration.py
"""

import httpx
import time

A2A_SERVER = "http://localhost:9000"
MARKETPLACE = "http://localhost:8500"

def test_direct_registration():
    """Register agent directly with A2A server, then check marketplace."""
    
    agent_payload = {
        "agent_id": "test_bypass_agent",
        "agent_type": "test",
        "endpoint": "http://localhost:8999/receive",
        "did": "did:key:z6MkTestBypass123",
        "public_key": "test-public-key",
        "capabilities": ["test_capability"],
        # NEW: Include governance metadata
        "source_repo": "https://github.com/test-org/test-agent",
        "owner_team": "Test Team",
        "description": "Test agent registered directly with A2A server"
    }
    
    print("=" * 60)
    print("TEST: Direct A2A Registration (Bypass Marketplace)")
    print("=" * 60)
    
    # Step 1: Register with A2A server directly
    print("\n1. Registering agent directly with A2A server...")
    try:
        resp = httpx.post(f"{A2A_SERVER}/agents/register", json=agent_payload, timeout=5.0)
        if resp.status_code == 200:
            print("   ✓ Agent registered with A2A server")
        elif resp.status_code == 400 and "already registered" in resp.text:
            print("   ⚠ Agent already exists in A2A registry")
        else:
            print(f"   ✗ Registration failed: {resp.status_code}")
            return
    except Exception as e:
        print(f"   ✗ A2A server not reachable: {e}")
        print("   → Start A2A server first: cd ap2_a2a_server && python server.py")
        return
    
    # Step 2: Check if agent appears in marketplace immediately
    print("\n2. Checking marketplace catalog (immediate)...")
    try:
        resp = httpx.get(f"{MARKETPLACE}/api/agents", timeout=5.0)
        agents = resp.json()
        agent = next((a for a in agents if a["id"] == "test_bypass_agent"), None)
        if agent:
            print(f"   ✓ Agent visible in marketplace")
            print(f"   - Status: {agent.get('status')}")
            print(f"   - Owner: {agent.get('owner_team')}")
            print(f"   - Source repo: {agent.get('source_repo')}")
            print(f"   - AI review: {'Yes' if agent.get('ai_review') else 'No (pending)'}")
        else:
            print("   ✗ Agent not yet visible")
    except Exception as e:
        print(f"   ✗ Marketplace not reachable: {e}")
        print("   → Start marketplace: python app.py")
        return
    
    # Step 3: Wait for background scanner
    print("\n3. Waiting 65 seconds for background governance scan...")
    print("   (Scanner runs every 60 seconds)")
    for i in range(13):
        time.sleep(5)
        print(f"   ... {(i+1)*5}s elapsed")
    
    # Step 4: Check if governance review was triggered
    print("\n4. Checking if governance review completed...")
    try:
        resp = httpx.get(f"{MARKETPLACE}/api/agents", timeout=5.0)
        agents = resp.json()
        agent = next((a for a in agents if a["id"] == "test_bypass_agent"), None)
        if agent:
            review = agent.get("ai_review")
            if review:
                print("   ✓ Governance review completed!")
                print(f"   - Summary: {review.get('summary', '')[:100]}...")
                print(f"   - Requires human review: {review.get('requires_human_review')}")
                print(f"   - Risk flags: {len(review.get('risk_flags', []))}")
                print(f"   - Status: {agent.get('status')}")
            else:
                print("   ⚠ No governance review yet (may need more time or Vertex AI not configured)")
        else:
            print("   ✗ Agent disappeared from catalog")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)
    print("\nExpected behavior:")
    print("- Agent appears in marketplace immediately")
    print("- Status: 'pending_review' initially")
    print("- After ~60s: AI governance review runs automatically")
    print("- Status changes to 'under_review' or 'active' based on review")
    print("\nView in UI: http://localhost:8500")
    print("=" * 60)

if __name__ == "__main__":
    test_direct_registration()
