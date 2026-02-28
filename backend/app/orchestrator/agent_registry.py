"""CRUD operations for agent records in SQLite."""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRecord, OrchestratorEventLog

logger = logging.getLogger(__name__)


async def create_agent(
    db: AsyncSession,
    *,
    name: str,
    assigned_repo: str | None = None,
    repo_path: str | None = None,
    role: str = "worker",
    desk_slot: int | None = None,
    personality: str | None = None,
    system_prompt: str | None = None,
) -> AgentRecord:
    """Create a new agent record."""
    agent_id = f"agent-{uuid.uuid4().hex[:8]}"
    agent = AgentRecord(
        agent_id=agent_id,
        name=name,
        role=role,
        assigned_repo=assigned_repo,
        repo_path=repo_path,
        desk_slot=desk_slot,
        personality=personality,
        system_prompt=system_prompt,
    )
    db.add(agent)
    await db.flush()

    # Log event
    db.add(OrchestratorEventLog(
        agent_id=agent_id,
        event_type="agent_created",
        data={"name": name, "repo": assigned_repo, "role": role},
    ))
    await db.commit()

    logger.info("Created agent %s (%s) for repo %s", agent_id, name, assigned_repo)
    return agent


async def get_agent(db: AsyncSession, agent_id: str) -> AgentRecord | None:
    """Get an agent by ID."""
    result = await db.execute(select(AgentRecord).where(AgentRecord.agent_id == agent_id))
    return result.scalar_one_or_none()


async def list_agents(db: AsyncSession) -> list[AgentRecord]:
    """List all agents."""
    result = await db.execute(select(AgentRecord).order_by(AgentRecord.desk_slot))
    return list(result.scalars().all())


async def update_agent_status(
    db: AsyncSession,
    agent_id: str,
    status: str,
    session_id: str | None = None,
) -> AgentRecord | None:
    """Update an agent's status."""
    agent = await get_agent(db, agent_id)
    if not agent:
        return None

    agent.status = status
    agent.last_active_at = datetime.now(UTC)
    if session_id is not None:
        agent.current_session_id = session_id

    db.add(OrchestratorEventLog(
        agent_id=agent_id,
        event_type="agent_status_changed",
        data={"status": status, "session_id": session_id},
    ))
    await db.commit()
    return agent


async def delete_agent(db: AsyncSession, agent_id: str) -> bool:
    """Delete an agent record."""
    agent = await get_agent(db, agent_id)
    if not agent:
        return False

    db.add(OrchestratorEventLog(
        agent_id=agent_id,
        event_type="agent_deleted",
        data={"name": agent.name},
    ))
    await db.delete(agent)
    await db.commit()

    logger.info("Deleted agent %s", agent_id)
    return True


async def assign_next_desk_slot(db: AsyncSession) -> int:
    """Find the next available desk slot (0-7)."""
    agents = await list_agents(db)
    used_slots = {a.desk_slot for a in agents if a.desk_slot is not None}
    for slot in range(8):
        if slot not in used_slots:
            return slot
    return len(agents) % 8  # Wrap around if all slots taken
