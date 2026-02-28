"""API routes for agent orchestration - spawn, kill, chat, list, mail, resume."""

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
from app.orchestrator.handoff import resume_agent, resume_all_agents
from app.orchestrator.mail_service import get_inbox, mark_read, send_mail
from app.orchestrator.pty_bridge import get_pty_bridge
from app.orchestrator.task_registry import list_tasks

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


# --- Resume / GUPP ---


@router.post("/agents/{agent_id}/resume")
async def resume_agent_endpoint(agent_id: str) -> dict[str, Any]:
    """Resume an agent with its last in-progress task (GUPP pattern)."""
    success = await resume_agent(agent_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to resume agent")
    return {"status": "resumed", "agent_id": agent_id}


@router.post("/resume-all")
async def resume_all() -> dict[str, Any]:
    """Resume all previously active agents on startup."""
    results = await resume_all_agents()
    return {"results": results}


# --- Mail ---


class MailRequest(BaseModel):
    to_agent_id: str
    subject: str
    body: str
    thread_id: str | None = None


@router.post("/agents/{agent_id}/mail")
async def send_mail_to_agent(agent_id: str, req: MailRequest) -> dict[str, Any]:
    """Send an async message to another agent."""
    async with AsyncSessionLocal() as db:
        mail = await send_mail(
            db,
            from_agent_id=agent_id,
            to_agent_id=req.to_agent_id,
            subject=req.subject,
            body=req.body,
            thread_id=req.thread_id,
        )
    return {"id": mail.id, "status": "sent"}


@router.get("/agents/{agent_id}/mail")
async def get_agent_mail(agent_id: str, unread: bool = True) -> list[dict[str, Any]]:
    """Get messages for an agent."""
    async with AsyncSessionLocal() as db:
        messages = await get_inbox(db, agent_id, unread_only=unread)
    return [
        {
            "id": m.id,
            "from": m.from_agent_id,
            "subject": m.subject,
            "body": m.body,
            "is_read": m.is_read,
            "thread_id": m.thread_id,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in messages
    ]


@router.post("/mail/{mail_id}/read")
async def mark_mail_read(mail_id: int) -> dict[str, Any]:
    """Mark a message as read."""
    async with AsyncSessionLocal() as db:
        ok = await mark_read(db, mail_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Mail not found")
    return {"status": "read", "mail_id": mail_id}


# --- Tasks ---


@router.get("/agents/{agent_id}/tasks")
async def get_agent_tasks(agent_id: str, status: str | None = None) -> list[dict[str, Any]]:
    """Get tasks assigned to an agent."""
    async with AsyncSessionLocal() as db:
        tasks = await list_tasks(db, agent_id=agent_id, status=status)
    return [
        {
            "task_id": t.task_id,
            "title": t.title,
            "status": t.status,
            "linear_issue_id": t.linear_issue_id,
            "linear_issue_url": t.linear_issue_url,
            "repo": t.repo,
            "priority": t.priority,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "started_at": t.started_at.isoformat() if t.started_at else None,
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        }
        for t in tasks
    ]
