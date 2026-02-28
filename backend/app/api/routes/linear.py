"""API routes for Linear issue management."""

import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db.database import AsyncSessionLocal
from app.orchestrator.agent_registry import get_agent, update_agent_status
from app.orchestrator.linear_service import get_linear_service
from app.orchestrator.pty_bridge import get_pty_bridge
from app.orchestrator.task_registry import create_task, get_task_by_linear_id, update_task_status

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/linear", tags=["linear"])


class AssignIssueRequest(BaseModel):
    agent_id: str
    prompt_override: str | None = None


class CreateIssueRequest(BaseModel):
    title: str
    description: str = ""
    priority: int = 3


@router.get("/status")
async def linear_status() -> dict[str, Any]:
    """Check if Linear integration is configured."""
    svc = get_linear_service()
    return {
        "enabled": svc.enabled,
        "team_id": svc.team_id or None,
        "project_id": svc.project_id or None,
    }


@router.get("/issues")
async def list_issues(
    state: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Fetch issues from Linear, optionally filtered by state name."""
    svc = get_linear_service()
    if not svc.enabled:
        raise HTTPException(status_code=503, detail="Linear not configured")

    state_names = [s.strip() for s in state.split(",")] if state else None
    return await svc.get_issues(state_names=state_names, limit=limit)


@router.get("/issues/{issue_id}")
async def get_issue(issue_id: str) -> dict[str, Any]:
    """Fetch a single Linear issue."""
    svc = get_linear_service()
    if not svc.enabled:
        raise HTTPException(status_code=503, detail="Linear not configured")

    issue = await svc.get_issue(issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    return issue


@router.post("/issues")
async def create_issue(req: CreateIssueRequest) -> dict[str, Any]:
    """Create a new Linear issue."""
    svc = get_linear_service()
    if not svc.enabled:
        raise HTTPException(status_code=503, detail="Linear not configured")

    issue = await svc.create_issue(
        title=req.title,
        description=req.description,
        priority=req.priority,
    )
    if not issue:
        raise HTTPException(status_code=500, detail="Failed to create issue")
    return issue


@router.post("/issues/{issue_id}/assign")
async def assign_issue_to_agent(issue_id: str, req: AssignIssueRequest) -> dict[str, Any]:
    """Assign a Linear issue to an agent — creates a task and sends the prompt."""
    svc = get_linear_service()
    if not svc.enabled:
        raise HTTPException(status_code=503, detail="Linear not configured")

    # Fetch issue details
    issue = await svc.get_issue(issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found in Linear")

    # Verify agent exists
    async with AsyncSessionLocal() as db:
        agent = await get_agent(db, req.agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

    # Create task record in DB
    task_id = str(uuid.uuid4())
    prompt = req.prompt_override or _build_prompt(issue)

    async with AsyncSessionLocal() as db:
        await create_task(
            db,
            task_id=task_id,
            title=issue.get("title", ""),
            description=issue.get("description", ""),
            linear_issue_id=issue_id,
            linear_issue_url=issue.get("url", ""),
            assigned_agent_id=req.agent_id,
            repo=agent.assigned_repo,
            prompt=prompt,
            priority=issue.get("priority", 3),
        )

    # Update Linear issue state to "In Progress"
    try:
        await svc.update_issue_state(issue_id, "In Progress")
    except Exception:
        logger.warning("Could not update Linear issue state to In Progress")

    # Send prompt to agent via PTY
    bridge = get_pty_bridge()
    try:
        await bridge.chat_agent(req.agent_id, prompt)
    except Exception as e:
        logger.error("Failed to send prompt to agent %s: %s", req.agent_id, e)
        raise HTTPException(status_code=500, detail=f"Agent chat failed: {e}") from e

    # Update agent status
    async with AsyncSessionLocal() as db:
        await update_agent_status(db, req.agent_id, "working")

    return {
        "task_id": task_id,
        "issue": issue.get("identifier", issue_id),
        "agent_id": req.agent_id,
        "status": "assigned",
    }


@router.post("/issues/{issue_id}/complete")
async def mark_issue_complete(issue_id: str) -> dict[str, Any]:
    """Mark a Linear issue as done (called when agent completes work)."""
    svc = get_linear_service()
    if not svc.enabled:
        raise HTTPException(status_code=503, detail="Linear not configured")

    # Update task in DB
    async with AsyncSessionLocal() as db:
        task = await get_task_by_linear_id(db, issue_id)
        if task:
            await update_task_status(db, task.task_id, "completed")

    # Update Linear issue state
    try:
        success = await svc.update_issue_state(issue_id, "Done")
    except Exception as e:
        logger.error("Failed to mark issue %s as Done: %s", issue_id, e)
        raise HTTPException(status_code=500, detail=f"Linear update failed: {e}") from e

    # Add a comment
    try:
        await svc.add_comment(issue_id, "Completed by AI Agent via Agent Office.")
    except Exception:
        pass  # Non-critical

    return {"issue_id": issue_id, "status": "done" if success else "state_not_found"}


@router.post("/webhook")
async def linear_webhook(payload: dict[str, Any]) -> dict[str, str]:
    """Handle incoming Linear webhooks (issue updates, comments)."""
    event_type = payload.get("type", "")
    data = payload.get("data", {})

    logger.info("Linear webhook: %s", event_type)

    # Handle issue state change to "Done" from external source
    if event_type == "Issue" and payload.get("action") == "update":
        state_name = data.get("state", {}).get("name", "")
        if state_name.lower() == "done":
            issue_id = data.get("id")
            if issue_id:
                async with AsyncSessionLocal() as db:
                    task = await get_task_by_linear_id(db, issue_id)
                    if task and task.status != "completed":
                        await update_task_status(db, task.task_id, "completed")
                        logger.info("Task %s auto-completed via Linear webhook", task.task_id)

    return {"status": "ok"}


def _build_prompt(issue: dict[str, Any]) -> str:
    """Build an agent prompt from a Linear issue."""
    identifier = issue.get("identifier", "")
    title = issue.get("title", "")
    description = issue.get("description", "") or ""

    labels = [l["name"] for l in issue.get("labels", {}).get("nodes", [])]
    labels_str = f"\nLabels: {', '.join(labels)}" if labels else ""

    return f"""You have been assigned Linear issue {identifier}: {title}
{labels_str}

{description}

Please work on this issue. When you are done, summarize what you did."""
