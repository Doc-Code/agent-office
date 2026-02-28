"""Async inter-agent messaging (Mail pattern from Gas Town)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MailRecord


async def send_mail(
    db: AsyncSession,
    *,
    from_agent_id: str | None = None,
    to_agent_id: str,
    subject: str,
    body: str,
    thread_id: str | None = None,
) -> MailRecord:
    """Send an async message to another agent."""
    mail = MailRecord(
        from_agent_id=from_agent_id,
        to_agent_id=to_agent_id,
        subject=subject,
        body=body,
        thread_id=thread_id or str(uuid.uuid4()),
    )
    db.add(mail)
    await db.commit()
    await db.refresh(mail)
    return mail


async def get_inbox(
    db: AsyncSession,
    agent_id: str,
    unread_only: bool = True,
) -> list[MailRecord]:
    """Get messages for an agent."""
    stmt = (
        select(MailRecord)
        .where(MailRecord.to_agent_id == agent_id)
        .order_by(MailRecord.created_at.desc())
    )
    if unread_only:
        stmt = stmt.where(MailRecord.is_read == False)  # noqa: E712
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def mark_read(db: AsyncSession, mail_id: int) -> bool:
    """Mark a message as read."""
    result = await db.execute(
        select(MailRecord).where(MailRecord.id == mail_id)
    )
    mail = result.scalar_one_or_none()
    if not mail:
        return False
    mail.is_read = True
    mail.read_at = datetime.now(UTC)
    await db.commit()
    return True


async def get_thread(db: AsyncSession, thread_id: str) -> list[MailRecord]:
    """Get all messages in a thread."""
    result = await db.execute(
        select(MailRecord)
        .where(MailRecord.thread_id == thread_id)
        .order_by(MailRecord.created_at.asc())
    )
    return list(result.scalars().all())
