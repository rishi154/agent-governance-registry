#!/usr/bin/env python3
"""Quick script to approve all pending agents for demo purposes."""

import os
import sys
from pathlib import Path

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)

BASE_URL = "http://localhost:8500"
API_KEY = os.getenv("MARKETPLACE_ADMIN_KEY")

if not API_KEY:
    print("ERROR: MARKETPLACE_ADMIN_KEY not set in .env")
    sys.exit(1)

headers = {"X-API-Key": API_KEY}

# Get review queue
resp = httpx.get(f"{BASE_URL}/api/review-queue", headers=headers)
resp.raise_for_status()
queue = resp.json()

print(f"Found {queue['count']} agents pending review\n")

for item in queue['items']:
    agent_id = item['id']
    print(f"Approving {agent_id}...")
    
    resp = httpx.post(
        f"{BASE_URL}/api/agents/{agent_id}/approve",
        headers=headers,
        json={"decision": "approve", "notes": "Auto-approved for demo"}
    )
    resp.raise_for_status()
    print(f"  ✓ Approved\n")

print("Done! Refresh the UI to see all agents.")
