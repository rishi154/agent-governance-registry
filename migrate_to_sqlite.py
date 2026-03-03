#!/usr/bin/env python3
"""
Migration script: enrichments.json → SQLite database
Run once to migrate existing data.
"""

import json
from pathlib import Path
from src.sqlite_store import sqlite_store

def migrate():
    enrichments_path = Path(__file__).parent / "data" / "enrichments.json"
    
    if not enrichments_path.exists():
        print("✓ No enrichments.json found - starting fresh with SQLite")
        return
    
    print(f"Migrating data from {enrichments_path}...")
    
    data = json.loads(enrichments_path.read_text())
    
    migrated = 0
    for agent_id, enrichment in data.items():
        try:
            sqlite_store.save(agent_id, enrichment)
            migrated += 1
            print(f"  ✓ Migrated: {agent_id}")
        except Exception as e:
            print(f"  ✗ Failed to migrate {agent_id}: {e}")
    
    print(f"\n✓ Migration complete: {migrated}/{len(data)} agents migrated")
    print(f"✓ Database created at: {sqlite_store.db_path}")
    print(f"\nBackup your enrichments.json before deleting it:")
    print(f"  cp {enrichments_path} {enrichments_path}.backup")

if __name__ == "__main__":
    migrate()
