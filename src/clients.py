"""
HTTP clients for MCP Server (port 9595) and A2A Server (port 9000).
Both servers may be offline — all methods return empty results gracefully.
"""

import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)

MCP_BASE_URL = "http://localhost:9595"
A2A_BASE_URL = "http://localhost:9000"
TIMEOUT = 3.0  # seconds — fast timeout so UI doesn't hang if server is down


class MCPClient:
    """Client for the rsagenticai-mcp-server."""

    def __init__(self, base_url: str = MCP_BASE_URL):
        self.base_url = base_url.rstrip("/")

    async def get_tools(self) -> list[dict]:
        """Fetch all registered tools from the MCP server.
        Adds an 'endpoint' field so each tool can be called directly.
        """
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(f"{self.base_url}/tools")
                resp.raise_for_status()
                data = resp.json()
                tools = data if isinstance(data, list) else data.get("tools", [])
                # Attach the callable endpoint for each MCP tool
                for tool in tools:
                    name = tool.get("name", "")
                    if name and "endpoint" not in tool:
                        tool["endpoint"] = f"{self.base_url}/tools/{name}"
                return tools
        except Exception as e:
            logger.warning(f"MCP server unavailable: {e}")
            return []

    async def get_plugins(self) -> list[dict]:
        """Fetch all loaded plugins from the MCP server."""
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(f"{self.base_url}/plugins")
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list):
                    return data
                return data.get("plugins", [])
        except Exception as e:
            logger.warning(f"MCP server unavailable (plugins): {e}")
            return []

    async def is_healthy(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(f"{self.base_url}/health")
                return resp.status_code == 200
        except Exception:
            return False


class A2AClient:
    """Client for the ap2_a2a_server."""

    def __init__(self, base_url: str = A2A_BASE_URL):
        self.base_url = base_url.rstrip("/")

    async def get_agents(self) -> list[dict]:
        """Fetch all registered agents from the A2A server."""
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(f"{self.base_url}/agents")
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list):
                    return data
                return data.get("agents", [])
        except Exception as e:
            logger.warning(f"A2A server unavailable: {e}")
            return []

    async def register_agent(self, payload: dict) -> dict:
        """Register a new agent with the A2A server."""
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(f"{self.base_url}/agents/register", json=payload)
            resp.raise_for_status()
            return resp.json()

    async def is_healthy(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(f"{self.base_url}/health")
                return resp.status_code == 200
        except Exception:
            return False
