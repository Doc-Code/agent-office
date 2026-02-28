"""Handoff — graceful agent restart with context preservation.

GUPP pattern: when an agent restarts, it automatically resumes
its last in-progress task using context from the database.
"""

import logging

from app.db.database import AsyncSessionLocal
from app.orchestrator.agent_registry import get_agent, list_agents, update_agent_status
from app.orchestrator.prompt_templates import build_gupp_prompt
from app.orchestrator.pty_bridge import get_pty_bridge
from app.orchestrator.task_registry import list_tasks

logger = logging.getLogger(__name__)


async def resume_agent(agent_id: str) -> bool:
    """Resume an agent with its last in-progress task (GUPP pattern).

    1. Look up the agent's last in-progress task
    2. Build a GUPP prompt from the task
    3. Spawn the agent with --continue flag
    4. Send the GUPP prompt

    Returns True if the agent was successfully resumed.
    """
    bridge = get_pty_bridge()

    async with AsyncSessionLocal() as db:
        agent = await get_agent(db, agent_id)
        if not agent:
            logger.warning("Cannot resume: agent %s not found", agent_id)
            return False

        if not agent.repo_path:
            logger.warning("Cannot resume: agent %s has no repo_path", agent_id)
            return False

        # Find last in-progress task for this agent
        tasks = await list_tasks(db, agent_id=agent_id, status="in_progress")
        task = tasks[0] if tasks else None

    # Spawn agent (with --continue to resume Claude Code conversation)
    try:
        await bridge.spawn_agent(
            agent_id=agent_id,
            working_directory=agent.repo_path,
            continue_conversation=True,
            personality=agent.personality,
        )
    except Exception as e:
        logger.error("Failed to spawn agent %s for resume: %s", agent_id, e)
        return False

    async with AsyncSessionLocal() as db:
        await update_agent_status(db, agent_id, "working")

    # If there's a task, send the GUPP prompt
    if task:
        prompt = build_gupp_prompt(task.title, task.description)
        logger.info("Resuming agent %s with task: %s", agent_id, task.title)
        try:
            await bridge.chat_agent(agent_id, prompt)
        except Exception:
            logger.warning("Failed to send GUPP to agent %s (may need warmup time)", agent_id)
    else:
        logger.info("Agent %s resumed with no pending task", agent_id)

    return True


async def resume_all_agents() -> dict[str, bool]:
    """Resume all previously active agents on startup (GUPP pattern).

    Checks for agents that were 'working' or 'idle' and restarts them.
    Returns a dict of agent_id -> success.
    """
    results: dict[str, bool] = {}

    async with AsyncSessionLocal() as db:
        agents = await list_agents(db)

    for agent in agents:
        if agent.status in ("working", "idle", "stuck") and agent.repo_path:
            logger.info("Auto-resuming agent: %s (%s)", agent.name, agent.agent_id)
            success = await resume_agent(agent.agent_id)
            results[agent.agent_id] = success

    return results
