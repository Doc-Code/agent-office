"""Supervisor — background loop that monitors agents and nudges stuck ones.

Gas Town pattern: periodic check, nudge idle agents, handoff stuck ones.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from app.db.database import AsyncSessionLocal
from app.db.models import AgentRecord
from app.orchestrator.agent_registry import list_agents, update_agent_status
from app.orchestrator.mail_service import send_mail
from app.orchestrator.pty_bridge import get_pty_bridge

logger = logging.getLogger(__name__)

# Thresholds
IDLE_NUDGE_MINUTES = 5
IDLE_HANDOFF_MINUTES = 15
CHECK_INTERVAL_SECONDS = 60


class Supervisor:
    """Background supervisor that monitors agent health."""

    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._running = False

    def start(self) -> None:
        """Start the supervisor background loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Supervisor started (check every %ds)", CHECK_INTERVAL_SECONDS)

    async def stop(self) -> None:
        """Stop the supervisor."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Supervisor stopped")

    async def _loop(self) -> None:
        """Main supervisor loop."""
        while self._running:
            try:
                await self._check_agents()
            except Exception:
                logger.exception("Supervisor check failed")
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)

    async def _check_agents(self) -> None:
        """Check all agents and take action on idle/stuck ones."""
        bridge = get_pty_bridge()
        pty_agents = await bridge.list_agents()

        async with AsyncSessionLocal() as db:
            agents = await list_agents(db)

        now = datetime.now(UTC)

        for agent in agents:
            if agent.status == "offline":
                continue

            pty = pty_agents.get(agent.agent_id, {})
            is_alive = pty.get("isAlive", False)

            # Agent record says working but PTY is dead
            if agent.status in ("working", "idle") and not is_alive:
                logger.warning(
                    "Agent %s (%s) PTY died — marking offline",
                    agent.name,
                    agent.agent_id,
                )
                async with AsyncSessionLocal() as db:
                    await update_agent_status(db, agent.agent_id, "offline")
                continue

            # Check idle time
            last_active = agent.last_active_at
            if not last_active:
                continue

            idle_minutes = (now - last_active).total_seconds() / 60

            if idle_minutes > IDLE_HANDOFF_MINUTES and agent.status == "stuck":
                # Agent has been stuck too long — send mail to supervisor/human
                logger.warning(
                    "Agent %s stuck for %.0f min — sending handoff mail",
                    agent.name,
                    idle_minutes,
                )
                async with AsyncSessionLocal() as db:
                    await send_mail(
                        db,
                        from_agent_id=None,  # System message
                        to_agent_id=agent.agent_id,
                        subject="Supervisor: You appear stuck",
                        body=(
                            f"You have been inactive for {idle_minutes:.0f} minutes. "
                            "Please report your status or ask for help."
                        ),
                    )

            elif idle_minutes > IDLE_NUDGE_MINUTES and agent.status == "working":
                # Nudge: agent might be stuck
                logger.info(
                    "Agent %s idle for %.0f min — nudging",
                    agent.name,
                    idle_minutes,
                )
                async with AsyncSessionLocal() as db:
                    await update_agent_status(db, agent.agent_id, "stuck")

                # Try to nudge via PTY
                if is_alive:
                    try:
                        await bridge.chat_agent(
                            agent.agent_id,
                            "Supervisor check-in: Are you still working? "
                            "Please report your progress or describe any blockers.",
                        )
                    except Exception:
                        logger.warning("Failed to nudge agent %s via PTY", agent.name)


_supervisor: Supervisor | None = None


def get_supervisor() -> Supervisor:
    global _supervisor  # noqa: PLW0603
    if _supervisor is None:
        _supervisor = Supervisor()
    return _supervisor
