from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class SessionRecord(Base):
    """Database model for Claude Code sessions."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_name: Mapped[str | None] = mapped_column(String, nullable=True)
    project_root: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    status: Mapped[str] = mapped_column(String, default="active")

    events: Mapped[list[EventRecord]] = relationship(
        "EventRecord", back_populates="session", cascade="all, delete-orphan"
    )


class EventRecord(Base):
    """Database model for events within a session."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String, ForeignKey("sessions.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    event_type: Mapped[str] = mapped_column(String)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)

    session: Mapped[SessionRecord] = relationship("SessionRecord", back_populates="events")


class TaskRecord(Base):
    """Database model for tasks within a session.

    Stores tasks from both the TodoWrite tool and the new task file system.
    Tasks are persisted to survive file system cleanup by Claude Code.
    """

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String, ForeignKey("sessions.id"), index=True)
    task_id: Mapped[str] = mapped_column(String)  # Original task ID (e.g., "1", "2")
    content: Mapped[str] = mapped_column(String)  # Subject/content of the task
    status: Mapped[str] = mapped_column(String)  # pending, in_progress, completed
    active_form: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    blocks: Mapped[str | None] = mapped_column(String, nullable=True)  # JSON-serialized list
    blocked_by: Mapped[str | None] = mapped_column(String, nullable=True)  # JSON-serialized list
    owner: Mapped[str | None] = mapped_column(String, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(String, nullable=True)  # JSON-serialized dict
    sort_order: Mapped[int] = mapped_column(default=0)  # For ordering tasks
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class UserPreference(Base):
    """Database model for user preferences.

    Stores key-value pairs for user preferences. Uses a flexible design
    to support adding new preferences without schema changes.
    """

    __tablename__ = "user_preferences"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


# --- Orchestrator Models ---


class AgentRecord(Base):
    """Persistent agent identity. Survives across sessions."""

    __tablename__ = "orchestrator_agents"

    agent_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, default="worker")  # worker | mayor | witness
    assigned_repo: Mapped[str | None] = mapped_column(String, nullable=True)
    repo_path: Mapped[str | None] = mapped_column(String, nullable=True)
    worktree_path: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="idle")  # idle | working | stuck | offline
    current_session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    hook_task_id: Mapped[str | None] = mapped_column(String, nullable=True)
    desk_slot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    personality: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    tasks_completed: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    last_active_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class WorkTaskRecord(Base):
    """Work items linked to Linear issues."""

    __tablename__ = "orchestrator_tasks"

    task_id: Mapped[str] = mapped_column(String, primary_key=True)
    linear_issue_id: Mapped[str | None] = mapped_column(String, nullable=True)
    linear_issue_url: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending | in_progress | blocked | completed | failed
    priority: Mapped[int] = mapped_column(Integer, default=3)  # 1=urgent, 4=low
    assigned_agent_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("orchestrator_agents.agent_id"), nullable=True
    )
    repo: Mapped[str | None] = mapped_column(String, nullable=True)
    parent_task_id: Mapped[str | None] = mapped_column(String, nullable=True)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    timeout_minutes: Mapped[int] = mapped_column(Integer, default=30)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MailRecord(Base):
    """Inter-agent async messaging."""

    __tablename__ = "orchestrator_mail"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    from_agent_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("orchestrator_agents.agent_id"), nullable=True
    )
    to_agent_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("orchestrator_agents.agent_id"), nullable=True
    )
    subject: Mapped[str | None] = mapped_column(String, nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    thread_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OrchestratorEventLog(Base):
    """Audit trail for orchestrator actions."""

    __tablename__ = "orchestrator_events_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    agent_id: Mapped[str | None] = mapped_column(String, nullable=True)
    event_type: Mapped[str] = mapped_column(String)
    data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
