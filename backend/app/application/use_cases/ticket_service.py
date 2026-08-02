from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.crew_orchestrator import crew_orchestrator
from app.agents.sub_agents import EscalationAgent, NotificationAgent
from app.core.config import get_settings
from app.domain.activity_notes import (
    NOTES_VIEWER_SUPPORTS,
    format_activity_notes_viewer,
    normalize_activity_notes,
    public_attachment,
)
from app.domain.ticket_status import STATUS_ORDER, can_transition
from app.domain.value_objects.ticket_state import TicketState
from app.infrastructure.db.models import EngineerModel, TicketModel
from app.infrastructure.llm.embeddings import cosine_similarity, embed_text
from app.infrastructure.n8n.client import n8n_client
from app.infrastructure.servicenow.client import servicenow_client
from app.infrastructure.vector.qdrant_store import vector_store
from app.infrastructure.monitoring.metrics_registry import inc_escalations, inc_tickets_created


def _sla_payload(t: TicketModel) -> dict[str, Any]:
    hours = {"P1": 2.0, "P2": 4.0, "P3": 6.0}.get(t.priority or "P3", 6.0)
    return {
        "due_at": t.sla_due_at,
        "breached": bool(t.sla_breached),
        "priority": t.priority,
        "hours": hours,
        "resolution_time": f"{int(hours)} Hours",
    }


def _serialize_ticket(t: TicketModel) -> dict[str, Any]:
    """Serialize canonical Ticket entity (+ compatibility aliases for UI)."""
    activity_notes = normalize_activity_notes(t.work_notes or [])
    attachments = [public_attachment(a, t.id) for a in (t.attachments or [])]
    images = [a for a in attachments if a.get("is_image")]
    embeddings = list(getattr(t, "embeddings", None) or [])
    knowledge_links = list(getattr(t, "knowledge_links", None) or [])
    related_incidents = list(getattr(t, "related_incidents", None) or [])
    sla = _sla_payload(t)
    return {
        # Canonical Ticket entity
        "id": t.id,
        "title": t.short_description,
        "description": t.description,
        "priority": t.priority,
        "status": t.state,
        "category": t.category,
        "subcategory": t.subcategory,
        "assigned_to": t.assigned_to,
        "created_by": t.caller,
        "created_date": t.created_at,
        "resolution_due": t.sla_due_at,
        "work_notes": t.work_notes or [],
        "attachments": attachments,
        "sla": sla,
        "embeddings": embeddings,
        "embeddings_dim": len(embeddings),
        "knowledge_links": knowledge_links,
        "related_incidents": related_incidents,
        # Compatibility / platform fields
        "number": t.number,
        "short_description": t.short_description,
        "state": t.state,
        "assignment_group": t.assignment_group,
        "configuration_item": t.configuration_item,
        "caller": t.caller,
        "ai_confidence": t.ai_confidence,
        "ai_summary": t.ai_summary,
        "root_cause_suggestion": t.root_cause_suggestion,
        "is_duplicate_of": t.is_duplicate_of,
        "duplicate_score": t.duplicate_score,
        "sla_due_at": t.sla_due_at,
        "sla_breached": t.sla_breached,
        "activity_notes": activity_notes,
        "activity_notes_viewer": format_activity_notes_viewer(activity_notes),
        "notes_viewer_supports": NOTES_VIEWER_SUPPORTS,
        "comments": t.comments or [],
        "images": images,
        "audit_logs": t.audit_logs or [],
        "metadata": t.ticket_metadata or {},
        "created_at": t.created_at,
        "updated_at": t.updated_at,
        "resolved_at": t.resolved_at,
        "closed_at": t.closed_at,
    }


def _activity_note(author: str, body: str, at: datetime | None = None) -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "author": author,
        "body": body,
        "format": "markdown",
        "image_ids": [],
        "attachment_ids": [],
        "is_internal": True,
        "created_at": (at or datetime.now(timezone.utc)).isoformat(),
    }


def _initial_activity_notes(
    *,
    short_description: str,
    summary: str,
    assigned_name: str | None,
    resolution_steps: list[str],
    now: datetime,
) -> list[dict[str, Any]]:
    """Seed Activity Notes on every ticket (Notes Viewer source)."""
    text = short_description.lower()
    notes: list[dict[str, Any]] = [
        _activity_note("system", "Ticket raised", now),
    ]
    if assigned_name:
        notes.append(_activity_note("assignment-agent", f"Assigned to {assigned_name}", now))

    # Domain-flavored starter notes so the Notes Viewer always has human-readable activity
    if "vpn" in text:
        notes.extend(
            [
                _activity_note("engineer", "Investigated VPN", now),
                _activity_note("engineer", "Restarted VPN Gateway", now),
            ]
        )
    elif summary:
        notes.append(_activity_note("ai-agent", summary[:240], now))

    if resolution_steps:
        notes.append(
            _activity_note(
                "resolution-agent",
                "Suggested resolution: " + "; ".join(resolution_steps[:3]),
                now,
            )
        )
    return notes


class TicketService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _next_number(self) -> str:
        count = await self.db.scalar(select(func.count()).select_from(TicketModel)) or 0
        return f"INC{100000 + int(count) + 1}"

    async def list_tickets(self) -> list[dict[str, Any]]:
        rows = (await self.db.scalars(select(TicketModel).order_by(TicketModel.created_at.desc()))).all()
        return [_serialize_ticket(r) for r in rows]

    async def get_ticket(self, ticket_id: str) -> dict[str, Any] | None:
        row = await self.db.get(TicketModel, ticket_id)
        return _serialize_ticket(row) if row else None

    async def create_and_triage(
        self,
        short_description: str,
        description: str,
        caller: str,
        configuration_item: str | None = None,
        sync_servicenow: bool = True,
        ai_draft: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        engineers = (await self.db.scalars(select(EngineerModel).where(EngineerModel.active.is_(True)))).all()
        eng_payload = [
            {
                "id": e.id,
                "name": e.name,
                "email": e.email,
                "skills": e.skills,
                "assignment_group": e.assignment_group,
                "team": e.assignment_group,
                "max_workload": e.max_workload,
                "current_workload": e.current_workload,
                "active": e.active,
                "available": True,
                "shift": "Day",
                "experience_years": 8 if e.name.lower() == "john" else 4,
            }
            for e in engineers
        ]
        existing = (await self.db.scalars(select(TicketModel).limit(100))).all()
        existing_payload = [
            {
                "id": t.id,
                "number": t.number,
                "short_description": t.short_description,
                "description": t.description,
            }
            for t in existing
        ]

        number = await self._next_number()
        orchestration = crew_orchestrator.run(
            {
                "short_description": short_description,
                "description": description,
                "configuration_item": configuration_item,
                "caller": caller,
                "engineers": eng_payload,
                "existing_tickets": existing_payload,
                "ticket_number": number,
            }
        )
        results = orchestration["results"]
        dup = results.get("duplicate_detection", {})
        # Sub Agent 4: if ≥90% similar, link existing ticket instead of creating new
        if dup.get("is_duplicate") and dup.get("duplicate_of"):
            linked = next(
                (t for t in existing if t.number == dup["duplicate_of"] or t.id == dup["duplicate_of"]),
                None,
            )
            if linked:
                return {
                    "ticket": _serialize_ticket(linked),
                    "agent_results": results,
                    "overall_confidence": orchestration["overall_confidence"],
                    "orchestrator": orchestration.get("orchestrator"),
                    "duplicate_linked": True,
                    "message": f"Linked to existing ticket {linked.number} (≥90% similar) instead of creating new.",
                }

        priority = results.get("priority", {}).get("priority", "P3")
        sla_due_raw = results.get("priority", {}).get("sla_due_at") or results.get("sla_monitor", {}).get("sla_due_at")
        sla_due = datetime.fromisoformat(sla_due_raw) if sla_due_raw else None
        assigned_to = results.get("assignment", {}).get("assigned_to")
        assignment_group = results.get("assignment", {}).get("team") or results.get("assignment", {}).get(
            "assignment_group", "IT Support"
        )
        category = results.get("classification", {}).get("category", "General")
        subcategory = results.get("classification", {}).get("subcategory", "")
        summary = results.get("summarization", {}).get("summary", "")
        rca = results.get("graphrag", {}).get("root_cause_suggestion", "")
        ci = results.get("graphrag", {}).get("configuration_item") or configuration_item

        # AI Ticket Creation draft overrides (Title/Category/Priority/Assignment/SLA/KB)
        if ai_draft:
            if ai_draft.get("title"):
                short_description = ai_draft["title"]
            if ai_draft.get("category"):
                category = ai_draft["category"]
            if ai_draft.get("subcategory"):
                subcategory = ai_draft["subcategory"]
            if ai_draft.get("priority"):
                priority = ai_draft["priority"]
                hours = {"P1": 2.0, "P2": 4.0, "P3": 6.0}.get(priority, 4.0)
                if ai_draft.get("sla"):
                    # e.g. "4 Hours"
                    try:
                        hours = float(str(ai_draft["sla"]).split()[0])
                    except (ValueError, IndexError):
                        pass
                sla_due = datetime.now(timezone.utc) + timedelta(hours=hours)
            if ai_draft.get("assignment"):
                assignment_group = ai_draft["assignment"]
            if ai_draft.get("assigned_to"):
                assigned_to = ai_draft["assigned_to"]
            if ai_draft.get("suggested_resolution"):
                summary = (
                    f"{summary}\nSuggested Resolution: {ai_draft['suggested_resolution']}".strip()
                    if summary
                    else f"Suggested Resolution: {ai_draft['suggested_resolution']}"
                )

        now = datetime.now(timezone.utc)
        state = TicketState.ASSIGNED.value if assigned_to else TicketState.NEW.value
        audit = [
            {
                "id": str(uuid4()),
                "actor": "master-agent",
                "action": "triage",
                "details": {"orchestrator": orchestration["orchestrator"], "confidence": orchestration["overall_confidence"]},
                "created_at": now.isoformat(),
            }
        ]
        if assigned_to:
            audit.append(
                {
                    "id": str(uuid4()),
                    "actor": "master-agent",
                    "action": "assign",
                    "details": {"assigned_to": assigned_to},
                    "created_at": now.isoformat(),
                }
            )

        # Canonical Ticket entity fields: embeddings, knowledge_links, related_incidents
        embedding_vec = embed_text(f"{short_description}\n{description}")
        knowledge_links = [
            {
                "id": a.get("id"),
                "title": a.get("title") or "KB",
                "source": a.get("source") or "kb",
                "score": a.get("score") or 0.0,
                "url": None,
            }
            for a in (results.get("rag_knowledge", {}).get("articles") or [])[:8]
        ]
        for sug in (results.get("resolution_suggestion", {}).get("suggestions") or [])[:5]:
            knowledge_links.append(
                {
                    "id": sug.get("id") or sug.get("title"),
                    "title": sug.get("title") or "Resolution ref",
                    "source": sug.get("source") or "kb",
                    "score": sug.get("score") or 0.0,
                    "url": None,
                }
            )
        if ai_draft and ai_draft.get("related_kb"):
            knowledge_links.insert(
                0,
                {
                    "id": ai_draft["related_kb"],
                    "title": ai_draft["related_kb"],
                    "source": "kb",
                    "score": 0.99,
                    "url": None,
                },
            )
        if ai_draft and ai_draft.get("suggested_resolution"):
            # Ensure activity notes include suggested resolution
            pass
        related_incidents: list[dict[str, Any]] = []
        if dup.get("duplicate_of"):
            related_incidents.append(
                {
                    "id": dup.get("duplicate_of"),
                    "number": dup.get("duplicate_of"),
                    "title": dup.get("duplicate_title") or "Possible duplicate",
                    "score": float(dup.get("duplicate_score") or 0.0),
                    "relation": "duplicate",
                }
            )
        for hit in vector_store.search(f"{short_description}\n{description}", limit=5):
            if hit.payload.get("source") in {"incident", "learned_incident"}:
                related_incidents.append(
                    {
                        "id": hit.id,
                        "number": hit.payload.get("number"),
                        "title": hit.payload.get("title") or "",
                        "score": round(float(hit.score), 4),
                        "relation": "similar",
                    }
                )

        ticket = TicketModel(
            id=str(uuid4()),
            number=number,
            short_description=short_description,  # title
            description=description,
            category=category,
            subcategory=subcategory,
            state=state,  # status
            priority=priority,
            assignment_group=assignment_group,
            assigned_to=assigned_to,
            configuration_item=ci,
            caller=caller,  # created_by
            ai_confidence=float(orchestration["overall_confidence"]),
            ai_summary=summary,
            root_cause_suggestion=rca,
            is_duplicate_of=dup.get("duplicate_of"),
            duplicate_score=float(dup.get("duplicate_score") or 0.0),
            sla_due_at=sla_due,  # resolution_due
            sla_breached=bool(results.get("sla_monitor", {}).get("breached", False)),
            work_notes=(
                _initial_activity_notes(
                    short_description=short_description,
                    summary=summary,
                    assigned_name=results.get("assignment", {}).get("assigned_name"),
                    resolution_steps=results.get("resolution_suggestion", {}).get("recommended_resolution") or [],
                    now=now,
                )
                + (
                    [
                        _activity_note(
                            "ai-ticket-creation",
                            f"**Suggested Resolution**\n\n{ai_draft['suggested_resolution']}\n\n"
                            f"**Related KB:** {ai_draft.get('related_kb', '—')}",
                            now,
                        )
                    ]
                    if ai_draft and ai_draft.get("suggested_resolution")
                    else []
                )
            ),
            comments=[],
            attachments=[],
            embeddings=embedding_vec,
            knowledge_links=knowledge_links,
            related_incidents=related_incidents,
            audit_logs=audit,
            ticket_metadata={
                "agent_results": results,
                "orchestrator": orchestration.get("orchestrator"),
                "agent_framework": orchestration.get("agent_framework", orchestration.get("orchestrator")),
                "crew_roles": orchestration.get("crew_roles", []),
                "resolution_suggestions": results.get("resolution_suggestion", {}).get("suggestions", []),
                "workflow_trace": list(orchestration.get("workflow_trace") or []),
                "entity": "Ticket",
                "ai_ticket_creation": ai_draft,
                "auto_created": False,
            },
            created_at=now,  # created_date
            updated_at=now,
        )
        self.db.add(ticket)

        if assigned_to:
            eng = next((e for e in engineers if e.email == assigned_to), None)
            if eng:
                eng.current_workload += 1

        await self.db.commit()
        await self.db.refresh(ticket)
        inc_tickets_created()

        vector_store.index_document(
            title=f"{ticket.number}: {ticket.short_description}",
            content=ticket.description,
            source="incident",
            doc_id=ticket.id,
        )

        n8n_result = await n8n_client.trigger_workflow(
            "ticket.created",
            {
                "id": ticket.id,
                "number": ticket.number,
                "title": ticket.short_description,
                "short_description": ticket.short_description,
                "description": ticket.description,
                "priority": ticket.priority,
                "category": ticket.category,
                "subcategory": ticket.subcategory,
                "assigned_to": ticket.assigned_to,
                "assignment_group": ticket.assignment_group,
                "caller": ticket.caller,
                "created_by": ticket.caller,
                "sync_servicenow": False,  # ServiceNow step also runs below; avoid double-create
                "engineers": eng_payload,
            },
        )

        workflow_trace = list(orchestration.get("workflow_trace") or [])
        # Ticket Workflow: Create ServiceNow Ticket → Notify Engineer → WIP → Resolution → Closed
        sn = None
        if sync_servicenow:
            sn = await servicenow_client.create_incident(_serialize_ticket(ticket))
            workflow_trace.append(
                {
                    "id": "create_servicenow",
                    "title": "Create ServiceNow Ticket",
                    "status": "completed",
                    "detail": sn.get("sys_id") or sn.get("number") or "synced",
                }
            )
        else:
            workflow_trace.append(
                {
                    "id": "create_servicenow",
                    "title": "Create ServiceNow Ticket",
                    "status": "skipped",
                    "detail": "sync_servicenow=false",
                }
            )

        notifier = NotificationAgent()
        assignment = results.get("assignment", {})
        priority_data = results.get("priority", {})
        eta = priority_data.get("resolution_time") or f"{priority_data.get('sla_hours', 6)} Hours"
        message = notifier.format_ticket_created(
            ticket.number,
            ticket.priority,
            assignment.get("assigned_name"),
            eta,
        )
        recipients = [r for r in [ticket.assigned_to, ticket.caller] if r] or ["ops@example.com"]
        notify_result = notifier.run(ticket.number, "ticket_created", recipients, message)
        results["notification"] = {**notify_result.data, "confidence": notify_result.confidence}
        workflow_trace.append(
            {
                "id": "notify_engineer",
                "title": "Notify Engineer",
                "status": "completed",
                "detail": notify_result.notes,
            }
        )
        # Ticket Status lifecycle remaining after create (current state already set)
        for title in STATUS_ORDER:
            step_id = title.lower().replace(" ", "_")
            if title == ticket.state:
                workflow_trace.append(
                    {"id": step_id, "title": title, "status": "completed", "kind": "status"}
                )
            else:
                # mark prior statuses completed for assigned tickets (NEW → ASSIGNED)
                idx = STATUS_ORDER.index(title)
                current_idx = STATUS_ORDER.index(ticket.state) if ticket.state in STATUS_ORDER else 0
                workflow_trace.append(
                    {
                        "id": step_id,
                        "title": title,
                        "status": "completed" if idx < current_idx else "pending",
                        "kind": "status",
                    }
                )

        meta = dict(ticket.ticket_metadata or {})
        if sn is not None:
            meta["servicenow"] = sn
        meta["workflow_trace"] = workflow_trace
        meta["agent_results"] = results
        meta["n8n_ticket_created"] = {
            "run_id": n8n_result.get("run_id"),
            "trace": n8n_result.get("trace"),
            "n8n_forward": n8n_result.get("n8n_forward"),
        }
        ticket.ticket_metadata = meta
        await self.db.commit()
        await self.db.refresh(ticket)

        return {
            "ticket": _serialize_ticket(ticket),
            "agent_results": results,
            "overall_confidence": orchestration["overall_confidence"],
            "orchestrator": orchestration["orchestrator"],
            "workflow_trace": workflow_trace,
            "n8n_workflow": n8n_result,
        }

    async def update_state(self, ticket_id: str, state: str, actor: str) -> dict[str, Any] | None:
        ticket = await self.db.get(TicketModel, ticket_id)
        if not ticket:
            return None
        if state not in {s.value for s in TicketState}:
            raise ValueError(f"Invalid state: {state}")
        if not can_transition(ticket.state, state):
            raise ValueError(
                f"Invalid transition: {ticket.state} → {state}. "
                f"Allowed path: {' → '.join(STATUS_ORDER)}"
            )
        now = datetime.now(timezone.utc)
        logs = list(ticket.audit_logs or [])
        logs.append(
            {
                "id": str(uuid4()),
                "actor": actor,
                "action": "state_change",
                "details": {"from": ticket.state, "to": state},
                "created_at": now.isoformat(),
            }
        )
        ticket.state = state
        ticket.updated_at = now
        ticket.audit_logs = logs
        # Activity Notes: every state change is recorded for the Notes Viewer
        notes = list(ticket.work_notes or [])
        notes.append(_activity_note(actor, state, now))
        ticket.work_notes = notes
        meta = dict(ticket.ticket_metadata or {})
        trace = list(meta.get("workflow_trace") or [])
        current_idx = STATUS_ORDER.index(state) if state in STATUS_ORDER else -1
        for step in trace:
            if step.get("kind") != "status":
                continue
            title = step.get("title")
            if title not in STATUS_ORDER:
                continue
            idx = STATUS_ORDER.index(title)
            if idx <= current_idx:
                step["status"] = "completed"
            elif step.get("status") != "completed":
                step["status"] = "pending"
        # ensure status steps exist in trace
        existing_status = {s.get("title") for s in trace if s.get("kind") == "status"}
        for title in STATUS_ORDER:
            if title not in existing_status:
                idx = STATUS_ORDER.index(title)
                trace.append(
                    {
                        "id": title.lower().replace(" ", "_"),
                        "title": title,
                        "status": "completed" if idx <= current_idx else "pending",
                        "kind": "status",
                    }
                )
        meta["workflow_trace"] = trace
        ticket.ticket_metadata = meta
        if state == TicketState.RESOLVED.value:
            ticket.resolved_at = now
            await self._learn_from_ticket(ticket, actor=actor)
        if state in {TicketState.COMPLETED.value, TicketState.CLOSED.value}:
            ticket.closed_at = now
            if ticket.assigned_to:
                eng = (
                    await self.db.scalars(
                        select(EngineerModel).where(EngineerModel.email == ticket.assigned_to)
                    )
                ).first()
                if eng and eng.current_workload > 0:
                    eng.current_workload -= 1
            await self._learn_from_ticket(ticket, actor=actor)
        await self.db.commit()
        await self.db.refresh(ticket)
        await n8n_client.trigger_workflow("ticket.state_changed", {"number": ticket.number, "state": state})
        return _serialize_ticket(ticket)

    async def _learn_from_ticket(self, ticket: TicketModel, actor: str) -> None:
        """Index resolved knowledge so future triage improves (continuous learning)."""
        resolution_bits = []
        for note in ticket.work_notes or []:
            if note.get("body"):
                resolution_bits.append(str(note["body"]))
        content = (
            f"Incident {ticket.number}\n"
            f"Category: {ticket.category}\n"
            f"Priority: {ticket.priority}\n"
            f"CI: {ticket.configuration_item}\n"
            f"Problem: {ticket.short_description}\n{ticket.description}\n"
            f"Root cause: {ticket.root_cause_suggestion}\n"
            f"Resolution notes:\n" + "\n".join(resolution_bits[-5:])
        )
        vector_store.index_document(
            title=f"Resolved {ticket.number}: {ticket.short_description}",
            content=content,
            source="learned_incident",
            doc_id=f"learned-{ticket.id}",
        )
        meta = dict(ticket.ticket_metadata or {})
        meta["learned_at"] = datetime.now(timezone.utc).isoformat()
        meta["learned_by"] = actor
        ticket.ticket_metadata = meta
        logs = list(ticket.audit_logs or [])
        logs.append(
            {
                "id": str(uuid4()),
                "actor": "learning-agent",
                "action": "learn_from_resolution",
                "details": {"indexed": True, "source": "learned_incident"},
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        ticket.audit_logs = logs

    async def search_previous_incidents(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        tickets = (await self.db.scalars(select(TicketModel).limit(200))).all()
        q_vec = embed_text(query)
        scored: list[tuple[float, TicketModel]] = []
        for t in tickets:
            text = f"{t.short_description}\n{t.description}\n{t.ai_summary}"
            score = cosine_similarity(q_vec, embed_text(text))
            scored.append((score, t))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, t in scored[:limit]:
            if score < 0.15:
                continue
            results.append(
                {
                    "id": t.id,
                    "number": t.number,
                    "short_description": t.short_description,
                    "priority": t.priority,
                    "state": t.state,
                    "category": t.category,
                    "ai_summary": t.ai_summary,
                    "root_cause_suggestion": t.root_cause_suggestion,
                    "score": round(score, 4),
                }
            )
        # Blend with vector store historical/learned docs
        for hit in vector_store.search(query, limit=limit):
            if hit.payload.get("source") in {"incident", "learned_incident", "kb"}:
                results.append(
                    {
                        "id": hit.id,
                        "number": hit.payload.get("title"),
                        "short_description": hit.payload.get("title"),
                        "priority": None,
                        "state": None,
                        "category": hit.payload.get("source"),
                        "ai_summary": (hit.payload.get("content") or "")[:240],
                        "root_cause_suggestion": "",
                        "score": round(hit.score, 4),
                    }
                )
        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:limit]

    async def escalate_overdue(self) -> dict[str, Any]:
        settings = get_settings()
        now = datetime.now(timezone.utc)
        open_states = {
            TicketState.NEW.value,
            TicketState.ASSIGNED.value,
            TicketState.WORK_IN_PROGRESS.value,
            TicketState.WAITING_FOR_CUSTOMER.value,
        }
        tickets = (await self.db.scalars(select(TicketModel))).all()
        escalated: list[dict[str, Any]] = []
        agent = EscalationAgent()

        def _aware(dt: datetime | None) -> datetime | None:
            if dt is None:
                return None
            return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)

        from app.agents.sub_agents import SLA_ESCALATION_LEAD_MINUTES, SLAMonitorAgent

        for ticket in tickets:
            due = _aware(ticket.sla_due_at)
            if ticket.state not in open_states or not due:
                continue
            minutes_remaining = (due - now).total_seconds() / 60.0
            # Sub Agent 7: escalate 30 minutes before breach (or when already breached)
            if minutes_remaining > SLA_ESCALATION_LEAD_MINUTES:
                continue
            meta = dict(ticket.ticket_metadata or {})
            if meta.get("escalated"):
                if minutes_remaining < 0:
                    ticket.sla_breached = True
                continue
            sla_view = SLAMonitorAgent().run(
                ticket.priority,
                created_at=_aware(ticket.created_at),
                sla_due_at=due.isoformat(),
            )
            result = agent.run(_serialize_ticket(ticket))
            old_priority = ticket.priority
            ticket.priority = result.data["to_priority"]
            ticket.sla_breached = minutes_remaining < 0
            hours = {"P1": settings.sla_p1_hours, "P2": settings.sla_p2_hours, "P3": settings.sla_p3_hours}[
                ticket.priority
            ]
            ticket.sla_due_at = now + timedelta(hours=hours / 2)
            meta["escalated"] = True
            meta["escalation"] = {**result.data, "sla": sla_view.data, "reason": "within_30_minutes_of_breach"}
            ticket.ticket_metadata = meta
            notes = list(ticket.work_notes or [])
            notes.append(
                {
                    "id": str(uuid4()),
                    "author": "sla-agent",
                    "body": f"{result.data['message']} (triggered ≤{SLA_ESCALATION_LEAD_MINUTES} min before breach)",
                    "created_at": now.isoformat(),
                    "is_internal": True,
                }
            )
            ticket.work_notes = notes
            logs = list(ticket.audit_logs or [])
            logs.append(
                {
                    "id": str(uuid4()),
                    "actor": "sla-agent",
                    "action": "escalate_before_breach",
                    "details": {
                        "from": old_priority,
                        "to": ticket.priority,
                        "minutes_remaining": round(minutes_remaining, 1),
                        "recipients": result.data["recipients"],
                    },
                    "created_at": now.isoformat(),
                }
            )
            ticket.audit_logs = logs
            NotificationAgent().run(
                ticket.number,
                "sla_escalation",
                result.data["recipients"],
                result.data["message"],
            )
            await n8n_client.trigger_workflow(
                "ticket.escalated",
                {"number": ticket.number, "from": old_priority, "to": ticket.priority},
            )
            escalated.append(
                {
                    "number": ticket.number,
                    "from_priority": old_priority,
                    "to_priority": ticket.priority,
                    "minutes_remaining": round(minutes_remaining, 1),
                    "recipients": result.data["recipients"],
                }
            )
        await self.db.commit()
        if escalated:
            inc_escalations(len(escalated))
        return {"escalated_count": len(escalated), "tickets": escalated}

    async def add_work_note(
        self,
        ticket_id: str,
        author: str,
        body: str,
        is_internal: bool = True,
        format: str = "markdown",
        image_ids: list[str] | None = None,
        attachment_ids: list[str] | None = None,
    ) -> dict | None:
        ticket = await self.db.get(TicketModel, ticket_id)
        if not ticket:
            return None
        notes = list(ticket.work_notes or [])
        notes.append(
            {
                "id": str(uuid4()),
                "author": author,
                "body": body,
                "format": format or "markdown",
                "image_ids": image_ids or [],
                "attachment_ids": attachment_ids or [],
                "is_internal": is_internal,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        ticket.work_notes = notes
        ticket.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(ticket)
        return _serialize_ticket(ticket)

    async def refresh_ai_summary(self, ticket_id: str) -> dict[str, Any] | None:
        """Regenerate AI Summary from ticket + activity notes for the Notes Viewer."""
        ticket = await self.db.get(TicketModel, ticket_id)
        if not ticket:
            return None
        from app.agents.sub_agents import SummarizationAgent

        activity = normalize_activity_notes(ticket.work_notes or [])
        notes_blob = "\n".join(f"- {n['date']}: {n['text']}" for n in activity[-12:])
        result = SummarizationAgent().run(
            {
                "short_description": ticket.short_description,
                "description": f"{ticket.description}\n\nActivity Notes:\n{notes_blob}",
            },
            {"priority": {"priority": ticket.priority}, "classification": {"category": ticket.category}},
        )
        summary = (result.data or {}).get("summary") or ticket.ai_summary
        ticket.ai_summary = summary
        ticket.updated_at = datetime.now(timezone.utc)
        notes = list(ticket.work_notes or [])
        notes.append(_activity_note("ai-summary", f"**AI Summary**\n\n{summary}"))
        # mark as markdown
        notes[-1]["format"] = "markdown"
        ticket.work_notes = notes
        await self.db.commit()
        await self.db.refresh(ticket)
        return _serialize_ticket(ticket)

    async def add_comment(self, ticket_id: str, author: str, body: str) -> dict | None:
        ticket = await self.db.get(TicketModel, ticket_id)
        if not ticket:
            return None
        comments = list(ticket.comments or [])
        comments.append(
            {
                "id": str(uuid4()),
                "author": author,
                "body": body,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        ticket.comments = comments
        ticket.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(ticket)
        return _serialize_ticket(ticket)

    async def dashboard(self) -> dict[str, Any]:
        tickets = (await self.db.scalars(select(TicketModel))).all()
        engineers = (await self.db.scalars(select(EngineerModel))).all()
        total = len(tickets) or 1
        breached = sum(1 for t in tickets if t.sla_breached)
        open_states = {
            TicketState.NEW.value,
            TicketState.ASSIGNED.value,
            TicketState.WORK_IN_PROGRESS.value,
            TicketState.WAITING_FOR_CUSTOMER.value,
        }
        closed_states = {
            TicketState.RESOLVED.value,
            TicketState.COMPLETED.value,
            TicketState.CLOSED.value,
        }
        lifecycle: dict[str, int] = {}
        for t in tickets:
            lifecycle[t.state] = lifecycle.get(t.state, 0) + 1
        by_priority: dict[str, int] = {"P1": 0, "P2": 0, "P3": 0}
        by_category: dict[str, int] = {}
        confidences = [t.ai_confidence for t in tickets]
        for t in tickets:
            by_priority[t.priority] = by_priority.get(t.priority, 0) + 1
            by_category[t.category] = by_category.get(t.category, 0) + 1
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        def _aware(dt: datetime | None) -> datetime | None:
            if dt is None:
                return None
            return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)

        open_tickets = [t for t in tickets if t.state in open_states]
        open_p1 = sum(1 for t in open_tickets if t.priority == "P1")
        open_p2 = sum(1 for t in open_tickets if t.priority == "P2")
        open_p3 = sum(1 for t in open_tickets if t.priority == "P3")
        resolved_today = sum(
            1
            for t in tickets
            if t.state in closed_states
            and _aware(t.resolved_at or t.closed_at or t.updated_at)
            and (_aware(t.resolved_at or t.closed_at or t.updated_at) or now) >= today_start
        )
        # Average resolution time (hours) for tickets with resolved_at
        resolution_hours: list[float] = []
        for t in tickets:
            created = _aware(t.created_at)
            done = _aware(t.resolved_at or t.closed_at)
            if created and done and done >= created:
                resolution_hours.append((done - created).total_seconds() / 3600.0)
        avg_resolution_hours = round(sum(resolution_hours) / len(resolution_hours), 2) if resolution_hours else 0.0

        # Agent performance from metadata / AI confidence / assignment volume
        agent_stats: dict[str, dict[str, Any]] = {
            "classification": {"runs": 0, "avg_confidence": 0.0},
            "priority": {"runs": 0, "avg_confidence": 0.0},
            "assignment": {"runs": 0, "avg_confidence": 0.0},
            "resolution": {"runs": 0, "avg_confidence": 0.0},
            "graphrag": {"runs": 0, "avg_confidence": 0.0},
        }
        agent_conf_sums: dict[str, list[float]] = {k: [] for k in agent_stats}
        for t in tickets:
            meta = t.ticket_metadata or {}
            results = meta.get("agent_results") or {}
            for key, alias in (
                ("classification", "classification"),
                ("priority", "priority"),
                ("assignment", "assignment"),
                ("resolution_suggestion", "resolution"),
                ("graphrag", "graphrag"),
            ):
                block = results.get(key) or {}
                if block:
                    agent_stats[alias]["runs"] += 1
                    conf = block.get("confidence")
                    if isinstance(conf, (int, float)):
                        agent_conf_sums[alias].append(float(conf))
            if meta.get("resolution_workflow"):
                agent_stats["resolution"]["runs"] += 1
                v = (meta.get("resolution_workflow") or {}).get("ai_verify") or {}
                if isinstance(v.get("confidence"), (int, float)):
                    agent_conf_sums["resolution"].append(float(v["confidence"]))
        for key, vals in agent_conf_sums.items():
            agent_stats[key]["avg_confidence"] = round(sum(vals) / len(vals), 4) if vals else 0.0

        # Engineer-level performance (tickets assigned / closed)
        engineer_perf = []
        for e in engineers:
            assigned = sum(1 for t in tickets if t.assigned_to == e.email)
            closed = sum(1 for t in tickets if t.assigned_to == e.email and t.state in closed_states)
            engineer_perf.append(
                {
                    "name": e.name,
                    "email": e.email,
                    "team": e.assignment_group,
                    "assigned": assigned,
                    "closed": closed,
                    "open_workload": e.current_workload,
                    "resolution_rate_pct": round(100 * closed / assigned, 1) if assigned else 0.0,
                }
            )
        engineer_perf.sort(key=lambda x: (x["closed"], x["assigned"]), reverse=True)

        ticket_dashboard = {
            "open_tickets": len(open_tickets),
            "p1_tickets": open_p1,
            "p2_tickets": open_p2,
            "p3_tickets": open_p3,
            "resolved_today": resolved_today,
            "sla_breaches": breached,
            "average_resolution_time_hours": avg_resolution_hours,
            "average_resolution_time_label": (
                f"{avg_resolution_hours:.1f}h" if resolution_hours else "—"
            ),
            "agent_performance": {
                "agents": agent_stats,
                "average_ai_confidence": round(sum(confidences) / len(confidences), 4) if confidences else 0,
                "engineers": engineer_perf[:8],
                "score": round(
                    (
                        (sum(confidences) / len(confidences) if confidences else 0) * 0.6
                        + (1 - breached / total) * 0.4
                    )
                    * 100,
                    1,
                ),
            },
            "cards": [
                {"id": "open_tickets", "title": "Open Tickets", "value": len(open_tickets)},
                {"id": "p1_tickets", "title": "P1 Tickets", "value": open_p1},
                {"id": "p2_tickets", "title": "P2 Tickets", "value": open_p2},
                {"id": "p3_tickets", "title": "P3 Tickets", "value": open_p3},
                {"id": "resolved_today", "title": "Resolved Today", "value": resolved_today},
                {"id": "sla_breaches", "title": "SLA Breaches", "value": breached},
                {
                    "id": "average_resolution_time",
                    "title": "Average Resolution Time",
                    "value": f"{avg_resolution_hours:.1f}h" if resolution_hours else "—",
                },
                {
                    "id": "agent_performance",
                    "title": "Agent Performance",
                    "value": f"{round((sum(confidences) / len(confidences) * 100) if confidences else 0)}%",
                },
            ],
        }

        # ---- Charts (last 14 days) ----
        days = 14
        day_keys: list[str] = []
        for i in range(days - 1, -1, -1):
            d = (now - timedelta(days=i)).date()
            day_keys.append(d.isoformat())

        created_by_day = {k: 0 for k in day_keys}
        resolved_by_day = {k: 0 for k in day_keys}
        for t in tickets:
            created = _aware(t.created_at)
            if created:
                key = created.date().isoformat()
                if key in created_by_day:
                    created_by_day[key] += 1
            done = _aware(t.resolved_at or t.closed_at)
            if done and t.state in closed_states:
                key = done.date().isoformat()
                if key in resolved_by_day:
                    resolved_by_day[key] += 1

        ticket_trend = [{"date": k, "created": created_by_day[k]} for k in day_keys]
        resolution_trend = [{"date": k, "resolved": resolved_by_day[k]} for k in day_keys]

        category_distribution = [
            {"name": name or "General", "value": count}
            for name, count in sorted(by_category.items(), key=lambda x: x[1], reverse=True)
        ] or [{"name": "None", "value": 0}]

        engineer_workload_chart = [
            {
                "name": e.name.split()[0] if e.name else e.email,
                "workload": e.current_workload,
                "capacity": e.max_workload,
                "utilization": round(100 * e.current_workload / max(e.max_workload, 1), 1),
            }
            for e in engineers
        ]

        compliant = max(len(tickets) - breached, 0)
        sla_compliance_chart = [
            {"name": "Compliant", "value": compliant},
            {"name": "Breached", "value": breached},
        ]

        # Knowledge Base usage: indexed corpus + ticket knowledge_links
        kb_source_counts = vector_store.source_counts()
        link_hits = 0
        for t in tickets:
            link_hits += len(getattr(t, "knowledge_links", None) or [])
        if link_hits:
            kb_source_counts["ticket_links"] = kb_source_counts.get("ticket_links", 0) + link_hits
        # Friendly labels
        kb_label = {
            "kb": "KB Articles",
            "sop": "SOP",
            "runbook": "Runbooks",
            "pdf": "PDFs",
            "incident": "Incidents",
            "learned_incident": "Learned Resolutions",
            "ticket_links": "Ticket KB Links",
            "unknown": "Other",
        }
        knowledge_base_usage = [
            {"name": kb_label.get(src, src), "value": count}
            for src, count in sorted(kb_source_counts.items(), key=lambda x: x[1], reverse=True)
        ] or [{"name": "No KB indexed", "value": 0}]

        # AI confidence scores — buckets + per-agent series
        ai_confidence_scores = [
            {"name": "High (≥80%)", "value": sum(1 for c in confidences if c >= 0.8)},
            {"name": "Medium (50–79%)", "value": sum(1 for c in confidences if 0.5 <= c < 0.8)},
            {"name": "Low (<50%)", "value": sum(1 for c in confidences if c < 0.5)},
        ]
        ai_confidence_by_agent = [
            {
                "name": name,
                "confidence": round(stats["avg_confidence"] * 100, 1),
                "runs": stats["runs"],
            }
            for name, stats in agent_stats.items()
        ]

        charts = {
            "ticket_trend": ticket_trend,
            "resolution_trend": resolution_trend,
            "category_distribution": category_distribution,
            "engineer_workload": engineer_workload_chart,
            "sla_compliance": sla_compliance_chart,
            "knowledge_base_usage": knowledge_base_usage,
            "ai_confidence_scores": ai_confidence_scores,
            "ai_confidence_by_agent": ai_confidence_by_agent,
        }
        ticket_dashboard["charts"] = charts

        return {
            "ticket_dashboard": ticket_dashboard,
            "charts": charts,
            "sla_compliance": {
                "total": len(tickets),
                "breached": breached,
                "compliance_pct": round(100 * (1 - breached / total), 2),
                "open_at_risk": sum(
                    1
                    for t in tickets
                    if t.state in open_states and _aware(t.sla_due_at) and _aware(t.sla_due_at) < now
                ),
            },
            "ticket_lifecycle": lifecycle,
            "engineer_workload": [
                {
                    "name": e.name,
                    "email": e.email,
                    "workload": e.current_workload,
                    "max_workload": e.max_workload,
                    "utilization_pct": round(100 * e.current_workload / max(e.max_workload, 1), 1),
                    "skills": e.skills,
                }
                for e in engineers
            ],
            "ai_confidence": {
                "average": round(sum(confidences) / len(confidences), 4) if confidences else 0,
                "high_confidence": sum(1 for c in confidences if c >= 0.8),
                "medium_confidence": sum(1 for c in confidences if 0.5 <= c < 0.8),
                "low_confidence": sum(1 for c in confidences if c < 0.5),
            },
            "incident_analytics": {
                "by_priority": by_priority,
                "by_category": by_category,
                "duplicates": sum(1 for t in tickets if t.is_duplicate_of),
                "resolved": sum(1 for t in tickets if t.state in closed_states),
            },
        }
