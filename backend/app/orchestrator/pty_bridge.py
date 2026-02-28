"""HTTP client to communicate with the PTY sidecar service."""

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class PtyBridge:
    """Async HTTP client for the PTY sidecar."""

    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.pty_sidecar_url
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(base_url=self.base_url, timeout=10.0)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def health(self) -> dict[str, Any]:
        """Check if sidecar is healthy."""
        client = await self._get_client()
        try:
            resp = await client.get("/health")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error("PTY sidecar health check failed: %s", e)
            return {"status": "error", "error": str(e)}

    async def spawn_agent(
        self,
        agent_id: str,
        working_directory: str,
        continue_conversation: bool = False,
        personality: str | None = None,
        initial_prompt: str | None = None,
    ) -> dict[str, Any]:
        """Spawn a new Claude Code agent."""
        client = await self._get_client()
        payload: dict[str, Any] = {"workingDirectory": working_directory}
        if continue_conversation:
            payload["continueConversation"] = True
        if personality:
            payload["personality"] = personality
        if initial_prompt:
            payload["initialPrompt"] = initial_prompt

        resp = await client.post(f"/agents/{agent_id}/spawn", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def kill_agent(self, agent_id: str) -> dict[str, Any]:
        """Kill an agent's process."""
        client = await self._get_client()
        resp = await client.delete(f"/agents/{agent_id}")
        resp.raise_for_status()
        return resp.json()

    async def chat_agent(self, agent_id: str, message: str) -> dict[str, Any]:
        """Send a chat message to an agent."""
        client = await self._get_client()
        resp = await client.post(f"/agents/{agent_id}/chat", json={"message": message})
        resp.raise_for_status()
        return resp.json()

    async def reset_agent(self, agent_id: str) -> dict[str, Any]:
        """Reset an agent (kill + respawn fresh)."""
        client = await self._get_client()
        resp = await client.post(f"/agents/{agent_id}/reset")
        resp.raise_for_status()
        return resp.json()

    async def get_agent_status(self, agent_id: str) -> dict[str, Any]:
        """Get PTY status of an agent."""
        client = await self._get_client()
        resp = await client.get(f"/agents/{agent_id}/status")
        resp.raise_for_status()
        return resp.json()

    async def list_agents(self) -> dict[str, Any]:
        """List all active PTY agents."""
        client = await self._get_client()
        resp = await client.get("/agents")
        resp.raise_for_status()
        return resp.json()


# Singleton instance
_bridge: PtyBridge | None = None


def get_pty_bridge() -> PtyBridge:
    """Get or create the PTY bridge singleton."""
    global _bridge
    if _bridge is None:
        _bridge = PtyBridge()
    return _bridge
