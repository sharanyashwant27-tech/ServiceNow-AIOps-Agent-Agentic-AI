from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="engineer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EngineerModel(Base):
    __tablename__ = "engineers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    skills: Mapped[list] = mapped_column(JSON, default=list)
    assignment_group: Mapped[str] = mapped_column(String(120), default="IT Support")
    max_workload: Mapped[int] = mapped_column(Integer, default=8)
    current_workload: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class TicketModel(Base):
    __tablename__ = "tickets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    short_description: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(120), default="General")
    subcategory: Mapped[str] = mapped_column(String(120), default="")
    state: Mapped[str] = mapped_column(String(60), default="New", index=True)
    priority: Mapped[str] = mapped_column(String(10), default="P3", index=True)
    assignment_group: Mapped[str] = mapped_column(String(120), default="")
    assigned_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    configuration_item: Mapped[str | None] = mapped_column(String(255), nullable=True)
    caller: Mapped[str] = mapped_column(String(255), default="system")
    ai_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    ai_summary: Mapped[str] = mapped_column(Text, default="")
    root_cause_suggestion: Mapped[str] = mapped_column(Text, default="")
    is_duplicate_of: Mapped[str | None] = mapped_column(String(40), nullable=True)
    duplicate_score: Mapped[float] = mapped_column(Float, default=0.0)
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sla_breached: Mapped[bool] = mapped_column(Boolean, default=False)
    work_notes: Mapped[list] = mapped_column(JSON, default=list)
    comments: Mapped[list] = mapped_column(JSON, default=list)
    attachments: Mapped[list] = mapped_column(JSON, default=list)
    audit_logs: Mapped[list] = mapped_column(JSON, default=list)
    embeddings: Mapped[list] = mapped_column(JSON, default=list)
    knowledge_links: Mapped[list] = mapped_column(JSON, default=list)
    related_incidents: Mapped[list] = mapped_column(JSON, default=list)
    ticket_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KnowledgeDocModel(Base):
    __tablename__ = "knowledge_docs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(120), default="kb")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
