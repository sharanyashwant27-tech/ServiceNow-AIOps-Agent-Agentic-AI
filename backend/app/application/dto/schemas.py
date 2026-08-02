from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    full_name: str
    role: str = "engineer"


class UserOut(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role: str


class TicketCreate(BaseModel):
    short_description: str | None = None
    title: str | None = None  # canonical alias for short_description
    description: str
    caller: str = "user@example.com"
    created_by: str | None = None  # canonical alias for caller
    configuration_item: str | None = None
    sync_servicenow: bool = True
    use_ai_draft: bool = False  # run AI Ticket Creation before triage

    def resolved_title(self) -> str:
        return (self.title or self.short_description or "").strip()

    def resolved_created_by(self) -> str:
        return (self.created_by or self.caller or "user@example.com").strip()


class AITicketCreateRequest(BaseModel):
    user_text: str = Field(min_length=3)


class TicketStateUpdate(BaseModel):
    state: str
    actor: str = "system"


class ResolutionWorkflowRequest(BaseModel):
    engineer: str = "engineer@example.com"
    resolution_note: str | None = None
    auto_close: bool = True


class WorkNoteCreate(BaseModel):
    author: str
    body: str
    is_internal: bool = True
    format: str = "markdown"
    image_ids: list[str] = Field(default_factory=list)
    attachment_ids: list[str] = Field(default_factory=list)


class CommentCreate(BaseModel):
    author: str
    body: str


class TicketOut(BaseModel):
    # Canonical Ticket entity
    id: str
    title: str = ""
    description: str
    priority: str
    status: str = ""
    category: str
    subcategory: str
    assigned_to: str | None
    assignment_group: str = ""
    assignment: str = "Unassigned"
    created_by: str = ""
    created_date: datetime | None = None
    completed_date: datetime | None = None
    resolution_due: datetime | None = None
    work_notes: list[dict[str, Any]]
    attachments: list[dict[str, Any]]
    sla: dict[str, Any] = Field(default_factory=dict)
    embeddings: list[float] = Field(default_factory=list)
    embeddings_dim: int = 0
    knowledge_links: list[dict[str, Any]] = Field(default_factory=list)
    related_incidents: list[dict[str, Any]] = Field(default_factory=list)
    # Compatibility aliases
    number: str
    short_description: str = ""
    state: str = ""
    configuration_item: str | None = None
    caller: str = ""
    ai_confidence: float = 0.0
    ai_summary: str = ""
    root_cause_suggestion: str = ""
    is_duplicate_of: str | None = None
    duplicate_score: float = 0.0
    sla_due_at: datetime | None = None
    sla_breached: bool = False
    activity_notes: list[dict[str, Any]] = Field(default_factory=list)
    activity_notes_viewer: str = ""
    notes_viewer_supports: list[dict[str, Any]] = Field(default_factory=list)
    comments: list[dict[str, Any]] = Field(default_factory=list)
    images: list[dict[str, Any]] = Field(default_factory=list)
    audit_logs: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    created_date_iso: str | None = None
    completed_date_iso: str | None = None
    resolved_at_iso: str | None = None
    closed_at_iso: str | None = None


class EngineerOut(BaseModel):
    id: str
    name: str
    email: str
    skills: list[str]
    assignment_group: str
    max_workload: int
    current_workload: int
    active: bool


class DashboardOut(BaseModel):
    ticket_dashboard: dict[str, Any] = Field(default_factory=dict)
    charts: dict[str, Any] = Field(default_factory=dict)
    sla_compliance: dict[str, Any]
    ticket_lifecycle: dict[str, Any]
    engineer_workload: list[dict[str, Any]]
    ai_confidence: dict[str, Any]
    incident_analytics: dict[str, Any]


class AgentRunResponse(BaseModel):
    ticket: TicketOut
    agent_results: dict[str, Any]
    overall_confidence: float
    orchestrator: str
