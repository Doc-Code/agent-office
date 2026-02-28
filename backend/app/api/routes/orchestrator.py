"""API routes for agent orchestration - spawn, kill, chat, list."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db.database import AsyncSessionLocal
from app.orchestrator.agent_registry import (
    assign_next_desk_slot,
    create_agent,
    delete_agent,
    get_agent,
    list_agents,
    update_agent_status,
)
from app.orchestrator.pty_bridge import get_pty_bridge

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


class SpawnAgentRequest(BaseModel):
    name: str
    repo: str | None = None
    repo_path: str | None = None
    personality: str | None = None
    initial_prompt: str | None = None
    desk_slot: int | None = None


class ChatRequest(BaseModel):
    message: str


class AgentResponse(BaseModel):
    agent_id: str
    name: str
    role: str
    status: str
    assigned_repo: str | None
    repo_path: str | None
    desk_slot: int | None
    pid: int | None = None
    is_alive: bool = False


@router.get("/health")
async def orchestrator_health() -> dict[str, Any]:
    """Check orchestrator and sidecar health."""
    bridge = get_pty_bridge()
    sidecar_status = await bridge.health()
    return {
        "orchestrator": "ok",
        "sidecar": sidecar_status,
    }


@router.get("/agents")
async def get_agents() -> list[AgentResponse]:
    """List all registered agents with their PTY status."""
    bridge = get_pty_bridge()
    pty_agents = await bridge.list_agents()

    async with AsyncSessionLocal() as db:
        agents = await list_agents(db)

    result = []
    for agent in agents:
        pty_status = pty_agents.get(agent.agent_id, {})
        result.append(AgentResponse(
            agent_id=agent.agent_id,
            name=agent.name,
            role=agent.role,
            status=agent.status,
            assigned_repo=agent.assigned_repo,
            repo_path=agent.repo_path,
            desk_slot=agent.desk_slot,
            pid=pty_status.get("pid"),
            is_alive=pty_status.get("isAlive", False),
        ))

    return result


@router.post("/agents", status_code=201)
async def spawn_agent(req: SpawnAgentRequest) -> AgentResponse:
    """Register a new agent and spawn its Claude Code process."""
    bridge = get_pty_bridge()

    async with AsyncSessionLocal() as db:
        # Assign desk slot
        desk_slot = req.desk_slot
        if desk_slot is None:
            desk_slot = await assign_next_desk_slot(db)

        # Create agent record
        agent = await create_agent(
            db,
            name=req.name,
            assigned_repo=req.repo,
            repo_path=req.repo_path,
            desk_slot=desk_slot,
            personality=req.personality,
        )

    # Spawn PTY process
    if not req.repo_path:
        raise HTTPException(status_code=400, detail="repo_path is required to spawn agent")

    try:
        pty_result = await bridge.spawn_agent(
            agent_id=agent.agent_id,
            working_directory=req.repo_path,
            personality=req.personality,
            initial_prompt=req.initial_prompt,
        )
    except Exception as e:
        logger.error("Failed to spawn PTY for %s: %s", agent.agent_id, e)
        # Update status to offline
        async with AsyncSessionLocal() as db:
            await update_agent_status(db, agent.agent_id, "offline")
        raise HTTPException(status_code=500, detail=f"PTY spawn failed: {e}") from e

    # Update status to working
    async with AsyncSessionLocal() as db:
        await update_agent_status(db, agent.agent_id, "working")

    return AgentResponse(
        agent_id=agent.agent_id,
        name=agent.name,
        role=agent.role,
        status="working",
        assigned_repo=agent.assigned_repo,
        repo_path=agent.repo_path,
        desk_slot=agent.desk_slot,
        pid=pty_result.get("pid"),
        is_alive=True,
    )


@router.delete("/agents/{agent_id}")
async def kill_agent(agent_id: str) -> dict[str, str]:
    """Kill an agent's PTY process and mark as offline."""
    bridge = get_pty_bridge()

    try:
        await bridge.kill_agent(agent_id)
    except Exception:
        pass  # Agent may already be dead

    async with AsyncSessionLocal() as db:
        agent = await get_agent(db, agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        await update_agent_status(db, agent_id, "offline")

    return {"status": "killed", "agent_id": agent_id}


@router.post("/agents/{agent_id}/chat")
async def chat_with_agent(agent_id: str, req: ChatRequest) -> dict[str, str]:
    """Send a chat message to an agent."""
    bridge = get_pty_bridge()

    async with AsyncSessionLocal() as db:
        agent = await get_agent(db, agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

    try:
        result = await bridge.chat_agent(agent_id, req.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat failed: {e}") from e

    return result


@router.post("/agents/{agent_id}/reset")
async def reset_agent(agent_id: str) -> dict[str, str]:
    """Reset an agent (kill + respawn fresh)."""
    bridge = get_pty_bridge()

    async with AsyncSessionLocal() as db:
        agent = await get_agent(db, agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

    try:
        result = await bridge.reset_agent(agent_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reset failed: {e}") from e

    async with AsyncSessionLocal() as db:
        await update_agent_status(db, agent_id, "working")

    return result


@router.delete("/agents/{agent_id}/record")
async def remove_agent_record(agent_id: str) -> dict[str, str]:
    """Delete an agent record permanently (after killing)."""
    bridge = get_pty_bridge()

    # Kill PTY if running
    try:
        await bridge.kill_agent(agent_id)
    except Exception:
        pass

    async with AsyncSessionLocal() as db:
        deleted = await delete_agent(db, agent_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Agent not found")

    return {"status": "deleted", "agent_id": agent_id}
