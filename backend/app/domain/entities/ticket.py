"""Canonical Ticket entity for the ServiceNow Agentic AIOps platform."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.domain.value_objects.ticket_state import Priority, TicketState

# Canonical Ticket field contract
TICKET_ENTITY_FIELDS = [
    "id",
    "title",
    "description",
    "priority",
    "status",
    "category",
    "subcategory",
    "assigned_to",
    "created_by",
    "created_date",
    "resolution_due",
    "work_notes",
    "attachments",
    "sla",
    "embeddings",
    "knowledge_links",
    "related_incidents",
]


@dataclass
class WorkNote:
    id: str
    author: str
    body: str
    created_at: datetime
    is_internal: bool = True
    format: str = "markdown"


@dataclass
class Comment:
    id: str
    author: str
    body: str
    created_at: datetime


@dataclass
class Attachment:
    id: str
    filename: str
    content_type: str
    size_bytes: int
    storage_path: str
    uploaded_by: str
    created_at: datetime


@dataclass
class AuditLog:
    id: str
    actor: str
    action: str
    details: dict[str, Any]
    created_at: datetime


@dataclass
class SLAInfo:
    due_at: datetime | None = None
    breached: bool = False
    priority: str = "P3"
    resolution_time: str = "6 Hours"
    hours: float = 6.0


@dataclass
class KnowledgeLink:
    id: str
    title: str
    source: str = "kb"
    score: float = 0.0
    url: str | None = None


@dataclass
class RelatedIncident:
    id: str
    number: str | None = None
    title: str = ""
    score: float = 0.0
    relation: str = "similar"  # similar | duplicate


@dataclass
class Ticket:
    """
    Ticket entity:

    id, title, description, priority, status, category, subcategory,
    assigned_to, created_by, created_date, resolution_due, work_notes,
    attachments, sla, embeddings, knowledge_links, related_incidents
    """

    title: str
    description: str
    id: str = field(default_factory=lambda: str(uuid4()))
    number: str = ""  # ServiceNow display number (INC…)
    priority: Priority = Priority.P3
    status: TicketState = TicketState.NEW
    category: str = "General"
    subcategory: str = ""
    assigned_to: str | None = None
    created_by: str = "system"
    created_date: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolution_due: datetime | None = None
    work_notes: list[WorkNote] = field(default_factory=list)
    attachments: list[Attachment] = field(default_factory=list)
    sla: SLAInfo = field(default_factory=SLAInfo)
    embeddings: list[float] = field(default_factory=list)
    knowledge_links: list[KnowledgeLink] = field(default_factory=list)
    related_incidents: list[RelatedIncident] = field(default_factory=list)

    # Operational / AI extensions (not in core contract but used by platform)
    assignment_group: str = ""
    configuration_item: str | None = None
    ai_confidence: float = 0.0
    ai_summary: str = ""
    root_cause_suggestion: str = ""
    comments: list[Comment] = field(default_factory=list)
    audit_logs: list[AuditLog] = field(default_factory=list)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    # Compatibility aliases
    @property
    def short_description(self) -> str:
        return self.title

    @property
    def state(self) -> TicketState:
        return self.status

    @property
    def caller(self) -> str:
        return self.created_by

    @property
    def created_at(self) -> datetime:
        return self.created_date

    @property
    def sla_due_at(self) -> datetime | None:
        return self.resolution_due or self.sla.due_at

    def transition_to(self, new_state: TicketState, actor: str) -> None:
        old = self.status
        self.status = new_state
        self.updated_at = datetime.now(timezone.utc)
        if new_state == TicketState.RESOLVED:
            self.resolved_at = self.updated_at
        if new_state in {TicketState.COMPLETED, TicketState.CLOSED}:
            self.closed_at = self.updated_at
        self.audit_logs.append(
            AuditLog(
                id=str(uuid4()),
                actor=actor,
                action="state_change",
                details={"from": old.value, "to": new_state.value},
                created_at=self.updated_at,
            )
        )
