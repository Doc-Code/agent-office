"""CRUD for WorkTaskRecord — task management linked to Linear issues."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import WorkTaskRecord


async def create_task(
    db: AsyncSession,
    *,
    task_id: str,
    title: str,
    description: str = "",
    linear_issue_id: str | None = None,
    linear_issue_url: str | None = None,
    assigned_agent_id: str | None = None,
    repo: str | None = None,
    prompt: str | None = None,
    priority: int = 3,
) -> WorkTaskRecord:
    task = WorkTaskRecord(
        task_id=task_id,
        title=title,
        description=description,
        linear_issue_id=linear_issue_id,
        linear_issue_url=linear_issue_url,
        assigned_agent_id=assigned_agent_id,
        repo=repo,
        prompt=prompt,
        priority=priority,
        status="in_progress",
        started_at=datetime.now(UTC),
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def get_task(db: AsyncSession, task_id: str) -> WorkTaskRecord | None:
    result = await db.execute(
        select(WorkTaskRecord).where(WorkTaskRecord.task_id == task_id)
    )
    return result.scalar_one_or_none()


async def get_task_by_linear_id(db: AsyncSession, linear_issue_id: str) -> WorkTaskRecord | None:
    result = await db.execute(
        select(WorkTaskRecord).where(WorkTaskRecord.linear_issue_id == linear_issue_id)
    )
    return result.scalar_one_or_none()


async def list_tasks(
    db: AsyncSession,
    *,
    agent_id: str | None = None,
    status: str | None = None,
) -> list[WorkTaskRecord]:
    stmt = select(WorkTaskRecord).order_by(WorkTaskRecord.created_at.desc())
    if agent_id:
        stmt = stmt.where(WorkTaskRecord.assigned_agent_id == agent_id)
    if status:
        stmt = stmt.where(WorkTaskRecord.status == status)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_task_status(
    db: AsyncSession,
    task_id: str,
    status: str,
    result: str | None = None,
) -> bool:
    task = await get_task(db, task_id)
    if not task:
        return False
    task.status = status
    if result is not None:
        task.result = result
    if status == "completed":
        task.completed_at = datetime.now(UTC)
    await db.commit()
    return True
