"""
SQLite-based storage for marketplace data.
Replaces enrichments.json with proper database.
"""

import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "data" / "marketplace.db"


class SQLiteStore:
    """Thread-safe SQLite storage for agents, reviews, and audit logs."""
    
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Create tables if they don't exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS agents (
                    agent_id TEXT PRIMARY KEY,
                    owner_team TEXT NOT NULL,
                    source_repo TEXT,
                    description TEXT,
                    status TEXT NOT NULL DEFAULT 'pending_review',
                    item_type TEXT NOT NULL DEFAULT 'agent',
                    discovery_method TEXT,
                    compliance TEXT,  -- JSON array
                    docs_url TEXT,
                    registered_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                
                CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL,
                    review_data TEXT NOT NULL,  -- JSON
                    reviewed_at TEXT NOT NULL,
                    FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
                );
                
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    actor TEXT,
                    timestamp TEXT NOT NULL,
                    details TEXT  -- JSON
                );
                
                CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status);
                CREATE INDEX IF NOT EXISTS idx_audit_agent ON audit_log(agent_id);
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
            """)
    
    @contextmanager
    def _get_conn(self):
        """Get database connection with automatic commit/rollback."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    # Columns that can be updated via save()
    _UPDATABLE_COLUMNS = {
        "owner_team", "source_repo", "description", "status",
        "discovery_method", "compliance", "docs_url", "item_type",
    }

    def save(self, agent_id: str, data: dict):
        """Save or update agent enrichment data.
        
        On UPDATE: only columns present in `data` are modified.
        Missing keys are left untouched (no more overwriting with defaults).
        On INSERT: missing keys get sensible defaults.
        """
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        
        with self._get_conn() as conn:
            existing = conn.execute(
                "SELECT agent_id FROM agents WHERE agent_id = ?", (agent_id,)
            ).fetchone()
            
            if existing:
                # Build SET clause from only the keys that were provided
                sets, vals = ["updated_at = ?"], [now]
                for col in self._UPDATABLE_COLUMNS:
                    if col in data:
                        val = json.dumps(data[col]) if col == "compliance" else data[col]
                        sets.append(f"{col} = ?")
                        vals.append(val)
                vals.append(agent_id)
                conn.execute(
                    f"UPDATE agents SET {', '.join(sets)} WHERE agent_id = ?",
                    vals,
                )
            else:
                # Insert — use defaults for missing keys
                compliance_json = json.dumps(data.get("compliance", []))
                conn.execute("""
                    INSERT INTO agents (
                        agent_id, owner_team, source_repo, description,
                        status, item_type, discovery_method, compliance,
                        docs_url, registered_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    agent_id,
                    data.get("owner_team", "Unassigned"),
                    data.get("source_repo", ""),
                    data.get("description", ""),
                    data.get("status", "pending_review"),
                    data.get("item_type", "agent"),
                    data.get("discovery_method", "marketplace"),
                    compliance_json,
                    data.get("docs_url", ""),
                    data.get("registered_at", now),
                    now,
                ))
            
            # Save review if present (append — never overwrite history)
            if "ai_review" in data:
                conn.execute("""
                    INSERT INTO reviews (agent_id, review_data, reviewed_at)
                    VALUES (?, ?, ?)
                """, (
                    agent_id,
                    json.dumps(data["ai_review"]),
                    data.get("ai_reviewed_at", now),
                ))
    
    def get(self, agent_id: str) -> dict:
        """Get agent enrichment data."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM agents WHERE agent_id = ?", (agent_id,)
            ).fetchone()
            
            if not row:
                return {}
            
            # Get latest review
            review_row = conn.execute("""
                SELECT review_data, reviewed_at FROM reviews
                WHERE agent_id = ?
                ORDER BY id DESC LIMIT 1
            """, (agent_id,)).fetchone()
            
            result = dict(row)
            result["compliance"] = json.loads(result["compliance"]) if result["compliance"] else []
            
            if review_row:
                result["ai_review"] = json.loads(review_row["review_data"])
                result["ai_reviewed_at"] = review_row["reviewed_at"]
            
            return result
    
    def all(self) -> dict:
        """Get all agents as dict (for backward compatibility)."""
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM agents").fetchall()
            
            result = {}
            for row in rows:
                agent_id = row["agent_id"]
                data = dict(row)
                data["compliance"] = json.loads(data["compliance"]) if data["compliance"] else []
                
                # Get latest review
                review_row = conn.execute("""
                    SELECT review_data, reviewed_at FROM reviews
                    WHERE agent_id = ?
                    ORDER BY id DESC LIMIT 1
                """, (agent_id,)).fetchone()
                
                if review_row:
                    data["ai_review"] = json.loads(review_row["review_data"])
                    data["ai_reviewed_at"] = review_row["reviewed_at"]
                
                result[agent_id] = data
            
            return result
    
    def update_status(self, agent_id: str, status: str, actor: str = "system"):
        """Update agent status and log to audit."""
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE agents SET status = ?, updated_at = ? WHERE agent_id = ?",
                (status, now, agent_id)
            )
            
            # Audit log
            conn.execute("""
                INSERT INTO audit_log (agent_id, action, actor, timestamp, details)
                VALUES (?, ?, ?, ?, ?)
            """, (
                agent_id,
                f"status_changed_to_{status}",
                actor,
                now,
                json.dumps({"new_status": status})
            ))
    
    def log_action(self, agent_id: str, action: str, actor: str, details: dict = None):
        """Log action to audit trail."""
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO audit_log (agent_id, action, actor, timestamp, details)
                VALUES (?, ?, ?, ?, ?)
            """, (
                agent_id,
                action,
                actor,
                now,
                json.dumps(details) if details else None
            ))
    
    def get_audit_log(self, agent_id: str = None, limit: int = 100) -> list[dict]:
        """Get audit log entries."""
        with self._get_conn() as conn:
            if agent_id:
                rows = conn.execute("""
                    SELECT * FROM audit_log
                    WHERE agent_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (agent_id, limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM audit_log
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (limit,)).fetchall()
            
            return [dict(row) for row in rows]


# Singleton instance
sqlite_store = SQLiteStore()
