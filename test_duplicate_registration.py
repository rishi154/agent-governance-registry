#!/usr/bin/env python3
"""
Test: Duplicate Registration Scenario
Tests what happens when an agent is registered both directly with A2A 
and through the marketplace.
"""

import httpx
import time
import json

A2A_SERVER = "http://localhost:9000"
MARKETPLACE = "http://localhost:8500"

def test_duplicate_registration():
    print("=" * 70)
    print("TEST: Duplicate Registration (A2A + Marketplace)")
    print("=" * 70)
    
    agent_id = "test_duplicate_agent"
    
    # Step 1: Register with A2A server first
    print("\n1. Registering agent directly with A2A server...")
    a2a_payload = {
        "agent_id": agent_id,
        "agent_type": "test",
        "endpoint": "http://localhost:8999/receive",
        "did": "did:key:z6MkTestDup",
        "public_key": "test-key",
        "capabilities": ["test_capability"],
        "source_repo": "https://github.com/test-org/test-agent",
        "owner_team": "A2A Team",  # Different team name
        "description": "Registered via A2A"
    }
    
    try:
        resp = httpx.post(f"{A2A_SERVER}/agents/register", json=a2a_payload, timeout=5.0)
        if resp.status_code in [200, 400]:
            print("   ✓ Agent in A2A registry")
        else:
            print(f"   ✗ Failed: {resp.status_code}")
            return
    except Exception as e:
        print(f"   ✗ A2A server not reachable: {e}")
        return
    
    # Step 2: Wait for background scanner to detect it
    print("\n2. Waiting 65 seconds for background scanner...")
    for i in range(13):
        time.sleep(5)
        print(f"   ... {(i+1)*5}s")
    
    # Step 3: Check auto-detected enrichment
    print("\n3. Checking auto-detected enrichment...")
    try:
        resp = httpx.get(f"{MARKETPLACE}/api/agents", timeout=5.0)
        agents = resp.json()
        agent = next((a for a in agents if a["id"] == agent_id), None)
        if agent:
            print(f"   ✓ Agent detected by scanner")
            print(f"   - Owner: {agent.get('owner_team')}")
            print(f"   - Status: {agent.get('status')}")
            print(f"   - AI review: {'Yes' if agent.get('ai_review') else 'No'}")
            
            auto_review = agent.get('ai_review')
            if auto_review:
                print(f"   - Review summary: {auto_review.get('summary', '')[:60]}...")
        else:
            print("   ✗ Agent not found")
            return
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return
    
    # Step 4: Now register through marketplace (duplicate)
    print("\n4. Registering SAME agent through marketplace...")
    marketplace_payload = {
        "agent_id": agent_id,
        "agent_type": "test",
        "endpoint": "http://localhost:8999/receive",
        "capabilities": ["test_capability"],
        "owner_team": "Marketplace Team",  # Different team name
        "compliance": ["Production-Ready"],
        "docs_url": "https://docs.example.com",
        "source_repo": "https://github.com/test-org/test-agent",
        "description": "Registered via Marketplace"
    }
    
    try:
        resp = httpx.post(
            f"{MARKETPLACE}/api/register/agent",
            json=marketplace_payload,
            timeout=30.0
        )
        result = resp.json()
        print(f"   ✓ Marketplace registration: {result.get('status')}")
        if result.get('note'):
            print(f"   ℹ️  {result.get('note')}")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return
    
    # Step 5: Verify final state
    print("\n5. Checking final agent state...")
    try:
        resp = httpx.get(f"{MARKETPLACE}/api/agents", timeout=5.0)
        agents = resp.json()
        agent = next((a for a in agents if a["id"] == agent_id), None)
        if agent:
            print(f"   ✓ Final state:")
            print(f"   - Owner: {agent.get('owner_team')}")
            print(f"   - Description: {agent.get('description')}")
            print(f"   - Status: {agent.get('status')}")
            print(f"   - Compliance: {agent.get('compliance')}")
            print(f"   - AI review present: {'Yes' if agent.get('ai_review') else 'No'}")
            
            review = agent.get('ai_review')
            if review:
                print(f"   - Review timestamp: {agent.get('ai_reviewed_at')}")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    
    print("\n" + "=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)
    print("\nExpected behavior:")
    print("✓ Auto-detected AI review is PRESERVED (not overwritten)")
    print("✓ Owner team updated to 'Marketplace Team'")
    print("✓ Description updated to 'Registered via Marketplace'")
    print("✓ Compliance tags added")
    print("✓ Status: 'updated' (not 'registered')")
    print("✓ No duplicate AI review run (saves time & cost)")
    print("\nView in UI: http://localhost:8500")
    print("=" * 70)

if __name__ == "__main__":
    test_duplicate_registration()
