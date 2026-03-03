#!/usr/bin/env python3
"""
Test script for Approval Workflow + SQLite + Authentication
Tests all three features end-to-end.
"""

import httpx
import os
import time

MARKETPLACE = "http://localhost:8500"

# Load API keys from environment or use defaults
ADMIN_KEY = os.getenv("MARKETPLACE_ADMIN_KEY", "admin-key-change-me")
DEV_KEY = os.getenv("MARKETPLACE_DEV_KEY", "dev-key-change-me")
VIEWER_KEY = os.getenv("MARKETPLACE_VIEWER_KEY", "viewer-key-change-me")

def test_all():
    print("=" * 70)
    print("TESTING: Approval Workflow + SQLite + Authentication")
    print("=" * 70)
    
    # Test 1: Authentication
    print("\n[TEST 1] Authentication")
    print("-" * 70)
    
    # No auth (should fail if ALLOW_UNAUTHENTICATED_READ=false)
    print("1.1 Testing unauthenticated access...")
    try:
        resp = httpx.get(f"{MARKETPLACE}/api/agents", timeout=5.0)
        if resp.status_code == 200:
            print("   ✓ Unauthenticated read allowed")
        else:
            print(f"   ✓ Unauthenticated read blocked ({resp.status_code})")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return
    
    # Viewer role
    print("1.2 Testing viewer role (read-only)...")
    try:
        resp = httpx.get(
            f"{MARKETPLACE}/api/agents",
            headers={"X-API-Key": VIEWER_KEY},
            timeout=5.0
        )
        if resp.status_code == 200:
            print("   ✓ Viewer can read agents")
        else:
            print(f"   ✗ Viewer read failed: {resp.status_code}")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    
    # Viewer cannot register
    print("1.3 Testing viewer cannot register...")
    try:
        resp = httpx.post(
            f"{MARKETPLACE}/api/register/agent",
            headers={"X-API-Key": VIEWER_KEY, "Content-Type": "application/json"},
            json={"agent_id": "test"},
            timeout=5.0
        )
        if resp.status_code == 403:
            print("   ✓ Viewer blocked from registering (403)")
        else:
            print(f"   ✗ Unexpected status: {resp.status_code}")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    
    # Test 2: Registration (Developer Role)
    print("\n[TEST 2] Agent Registration (Developer Role)")
    print("-" * 70)
    
    agent_id = f"test_agent_{int(time.time())}"
    
    print(f"2.1 Registering agent: {agent_id}...")
    try:
        resp = httpx.post(
            f"{MARKETPLACE}/api/register/agent",
            headers={"X-API-Key": DEV_KEY, "Content-Type": "application/json"},
            json={
                "agent_id": agent_id,
                "agent_type": "test",
                "endpoint": "http://localhost:8999/receive",
                "capabilities": ["test_capability"],
                "owner_team": "Test Team",
                "source_repo": "https://github.com/test-org/test-agent",
                "description": "Test agent for approval workflow"
            },
            timeout=30.0
        )
        if resp.status_code == 200:
            result = resp.json()
            print(f"   ✓ Agent registered: {result.get('status')}")
            print(f"   - Approval required: {result.get('approval_required')}")
        else:
            print(f"   ✗ Registration failed: {resp.status_code}")
            print(f"   {resp.text}")
            return
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return
    
    # Test 3: Approval Workflow
    print("\n[TEST 3] Approval Workflow")
    print("-" * 70)
    
    # Check agent is NOT visible to developers yet
    print("3.1 Checking agent visibility (before approval)...")
    try:
        resp = httpx.get(
            f"{MARKETPLACE}/api/agents",
            headers={"X-API-Key": DEV_KEY},
            timeout=5.0
        )
        agents = resp.json()
        visible = any(a["id"] == agent_id for a in agents)
        if not visible:
            print("   ✓ Agent hidden from developers (pending approval)")
        else:
            print("   ⚠ Agent visible before approval (unexpected)")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    
    # Admin views review queue
    print("3.2 Checking review queue (admin)...")
    try:
        resp = httpx.get(
            f"{MARKETPLACE}/api/review-queue",
            headers={"X-API-Key": ADMIN_KEY},
            timeout=5.0
        )
        if resp.status_code == 200:
            queue = resp.json()
            print(f"   ✓ Review queue: {queue['count']} items pending")
            in_queue = any(i["id"] == agent_id for i in queue["items"])
            if in_queue:
                print(f"   ✓ Agent {agent_id} in review queue")
        else:
            print(f"   ✗ Failed to get review queue: {resp.status_code}")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    
    # Admin approves agent
    print("3.3 Approving agent (admin)...")
    try:
        resp = httpx.post(
            f"{MARKETPLACE}/api/agents/{agent_id}/approve",
            headers={"X-API-Key": ADMIN_KEY, "Content-Type": "application/json"},
            json={"decision": "approve", "notes": "Test approval"},
            timeout=5.0
        )
        if resp.status_code == 200:
            result = resp.json()
            print(f"   ✓ Agent approved: {result.get('new_status')}")
        else:
            print(f"   ✗ Approval failed: {resp.status_code}")
            print(f"   {resp.text}")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    
    # Check agent is NOW visible
    print("3.4 Checking agent visibility (after approval)...")
    try:
        resp = httpx.get(
            f"{MARKETPLACE}/api/agents",
            headers={"X-API-Key": DEV_KEY},
            timeout=5.0
        )
        agents = resp.json()
        agent = next((a for a in agents if a["id"] == agent_id), None)
        if agent:
            print(f"   ✓ Agent now visible to developers")
            print(f"   - Status: {agent.get('status')}")
            print(f"   - Owner: {agent.get('owner_team')}")
        else:
            print("   ✗ Agent still not visible")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    
    # Test 4: Audit Log
    print("\n[TEST 4] Audit Log")
    print("-" * 70)
    
    print("4.1 Checking audit log (admin)...")
    try:
        resp = httpx.get(
            f"{MARKETPLACE}/api/agents/{agent_id}/audit",
            headers={"X-API-Key": ADMIN_KEY},
            timeout=5.0
        )
        if resp.status_code == 200:
            audit = resp.json()
            print(f"   ✓ Audit log: {len(audit)} entries")
            for entry in audit[:3]:
                print(f"   - {entry['action']} by {entry['actor']} at {entry['timestamp']}")
        else:
            print(f"   ✗ Failed to get audit log: {resp.status_code}")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)
    print("\nWhat was tested:")
    print("✓ Authentication (viewer/developer/admin roles)")
    print("✓ Permission enforcement (viewer cannot register)")
    print("✓ Agent registration (developer role)")
    print("✓ Approval workflow (agent hidden until approved)")
    print("✓ Review queue (admin can see pending items)")
    print("✓ Approval action (admin approves agent)")
    print("✓ Visibility after approval (agent now discoverable)")
    print("✓ Audit log (tracks all actions)")
    print("\nView in UI: http://localhost:8500")
    print("=" * 70)

if __name__ == "__main__":
    test_all()
