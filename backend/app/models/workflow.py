import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    # 仅用于类型检查；运行时由 SQLAlchemy registry 解析字符串关系
    from app.models.execution import Execution
    from app.models.user import User


class WorkflowStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"


class StepType(str, Enum):
    TRIGGER = "trigger"
    TOOL = "tool"
    CONDITION = "condition"
    APPROVAL = "approval"


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    dag_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=WorkflowStatus.DRAFT)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    user: Mapped["User"] = relationship("User", back_populates="workflows")
    steps: Mapped[list["Step"]] = relationship(
        "Step", back_populates="workflow", lazy="selectin", cascade="all, delete-orphan"
    )
    schedule: Mapped["Schedule | None"] = relationship(
        "Schedule", back_populates="workflow", uselist=False, cascade="all, delete-orphan"
    )
    executions: Mapped[list["Execution"]] = relationship(
        "Execution", back_populates="workflow", lazy="selectin", cascade="all, delete-orphan"
    )

    # ---- 调度相关的计算属性（供 response_model 读取）----
    @property
    def cron_expr(self) -> str | None:
        sched = self.schedule
        return sched.cron_expr if sched else None

    @property
    def schedule_enabled(self) -> bool | None:
        sched = self.schedule
        return sched.enabled if sched else None

    @property
    def next_run(self) -> datetime | None:
        sched = self.schedule
        return sched.next_run if sched else None


class Step(Base):
    __tablename__ = "steps"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    step_type: Mapped[str] = mapped_column(String(20), nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    position: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    order: Mapped[int] = mapped_column(Integer, default=0)

    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="steps")


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    cron_expr: Mapped[str] = mapped_column(String(100), nullable=False)
    next_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="schedule")
