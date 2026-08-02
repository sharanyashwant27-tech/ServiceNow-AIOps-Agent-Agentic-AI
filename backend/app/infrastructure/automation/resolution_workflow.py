"""
Resolution Workflow:

Engineer → Resolve Ticket → AI Verify → Customer Email → Close Ticket → Store Embedding
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.resolution_workflow import RESOLUTION_WORKFLOW
from app.domain.ticket_status import STATUS_ORDER, can_transition
from app.domain.value_objects.ticket_state import TicketState
from app.infrastructure.db.models import EngineerModel, TicketModel
from app.infrastructure.llm.embeddings import embed_text
from app.infrastructure.n8n.client import n8n_client
from app.infrastructure.notifications.channels import notification_channels
from app.infrastructure.vector.qdrant_store import vector_store
from sqlalchemy import select

logger = logging.getLogger(__name__)

_RUN_LOGS: list[dict[str, Any]] = []


class ResolutionWorkflow:
    def definition(self) -> dict[str, Any]:
        return RESOLUTION_WORKFLOW

    def logs(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(reversed(_RUN_LOGS[-limit:]))

    def _ai_verify(self, ticket: TicketModel) -> dict[str, Any]:
        """Heuristic AI verification that resolution evidence exists and looks complete."""
        notes = ticket.work_notes or []
        note_text = " ".join(str(n.get("body") or "") for n in notes).lower()
        description = f"{ticket.short_description} {ticket.description}".lower()
        checks = {
            "has_work_notes": len(notes) > 0,
            "has_resolution_language": any(
                k in note_text for k in ("resolved", "fixed", "restart", "applied", "restored", "completed", "cache")
            ),
            "has_ai_summary": bool((ticket.ai_summary or "").strip()),
            "not_duplicate_unresolved": not (
                ticket.is_duplicate_of and ticket.state not in {TicketState.RESOLVED.value, TicketState.CLOSED.value}
            ),
            "priority_present": bool(ticket.priority),
        }
        # Domain boosts
        if "outlook" in description and "cache" in note_text:
            checks["outlook_cache_addressed"] = True
        if "vpn" in description and ("vpn" in note_text or "gateway" in note_text):
            checks["vpn_addressed"] = True

        passed = sum(1 for v in checks.values() if v)
        total = len(checks)
        score = round(passed / max(total, 1), 4)
        verified = score >= 0.6 and checks["has_work_notes"]
        reasons = [k for k, v in checks.items() if not v]
        return {
            "verified": verified,
            "confidence": score,
            "checks": checks,
            "failed_checks": reasons,
            "summary": (
                "AI Verify passed — resolution evidence looks sufficient."
                if verified
                else "AI Verify needs attention — missing resolution evidence: " + ", ".join(reasons or ["unknown"])
            ),
        }

    async def run(
        self,
        db: AsyncSession,
        ticket_id: str,
        engineer: str,
        resolution_note: str | None = None,
        auto_close: bool = True,
    ) -> dict[str, Any]:
        ticket = await db.get(TicketModel, ticket_id)
        if not ticket:
            raise ValueError("Ticket not found")

        now = datetime.now(timezone.utc)
        run_id = str(uuid4())
        trace: list[dict[str, Any]] = []

        # 1. Engineer
        trace.append(
            {
                "id": "engineer",
                "title": "Engineer",
                "status": "completed",
                "detail": engineer,
            }
        )

        # Optional resolution note from engineer
        if resolution_note and resolution_note.strip():
            notes = list(ticket.work_notes or [])
            notes.append(
                {
                    "id": str(uuid4()),
                    "author": engineer,
                    "body": resolution_note.strip(),
                    "format": "markdown",
                    "created_at": now.isoformat(),
                    "is_internal": True,
                }
            )
            ticket.work_notes = notes

        # 2. Resolve Ticket
        if ticket.state != TicketState.RESOLVED.value:
            if not can_transition(ticket.state, TicketState.RESOLVED.value):
                # Force path through WIP if needed for demo flexibility from Assigned
                if can_transition(ticket.state, TicketState.WORK_IN_PROGRESS.value):
                    ticket.state = TicketState.WORK_IN_PROGRESS.value
                if not can_transition(ticket.state, TicketState.RESOLVED.value):
                    raise ValueError(f"Cannot resolve from state {ticket.state}")
            logs = list(ticket.audit_logs or [])
            logs.append(
                {
                    "id": str(uuid4()),
                    "actor": engineer,
                    "action": "state_change",
                    "details": {"from": ticket.state, "to": TicketState.RESOLVED.value, "workflow": "resolution"},
                    "created_at": now.isoformat(),
                }
            )
            ticket.audit_logs = logs
            ticket.state = TicketState.RESOLVED.value
            ticket.resolved_at = now
        trace.append(
            {
                "id": "resolve_ticket",
                "title": "Resolve Ticket",
                "status": "completed",
                "detail": f"{ticket.number} → Resolved",
            }
        )

        # 3. AI Verify
        verify = self._ai_verify(ticket)
        notes = list(ticket.work_notes or [])
        notes.append(
            {
                "id": str(uuid4()),
                "author": "ai-verify",
                "body": f"**AI Verify**\n\n{verify['summary']}\n\nConfidence: {int(verify['confidence'] * 100)}%",
                "format": "markdown",
                "created_at": now.isoformat(),
                "is_internal": True,
            }
        )
        ticket.work_notes = notes
        trace.append(
            {
                "id": "ai_verify",
                "title": "AI Verify",
                "status": "completed" if verify["verified"] else "failed",
                "detail": verify["summary"],
                "data": verify,
            }
        )

        # 4. Customer Email
        customer = ticket.caller or "customer@example.com"
        email_body = (
            f"Hello,\n\n"
            f"Your ticket {ticket.number} ({ticket.short_description}) has been resolved.\n\n"
            f"AI verification: {'Passed' if verify['verified'] else 'Pending review'} "
            f"({int(verify['confidence'] * 100)}% confidence).\n\n"
            f"Summary: {(ticket.ai_summary or 'Resolution applied by engineering.')[:400]}\n\n"
            f"If the issue persists, reply to this email or reopen the ticket.\n\n"
            f"— ServiceNow AIOps"
        )
        email_result = notification_channels.send_smtp(
            subject=f"[AIOps] Ticket {ticket.number} Resolved",
            message=email_body,
            recipients=[customer],
        )
        await notification_channels.send_slack(
            subject=f"Ticket Resolved {ticket.number}",
            message=email_body,
        )
        trace.append(
            {
                "id": "customer_email",
                "title": "Customer Email",
                "status": "completed",
                "detail": f"to={customer} sent={email_result.get('sent')} mocked={email_result.get('mocked', False)}",
                "data": email_result,
            }
        )

        # 5. Close Ticket (if AI verify passed)
        closed = False
        if auto_close and verify["verified"] and can_transition(ticket.state, TicketState.CLOSED.value):
            prev = ticket.state
            ticket.state = TicketState.CLOSED.value
            ticket.closed_at = now
            closed = True
            logs = list(ticket.audit_logs or [])
            logs.append(
                {
                    "id": str(uuid4()),
                    "actor": "resolution-workflow",
                    "action": "state_change",
                    "details": {"from": prev, "to": TicketState.CLOSED.value, "workflow": "resolution"},
                    "created_at": now.isoformat(),
                }
            )
            ticket.audit_logs = logs
            if ticket.assigned_to:
                eng = (
                    await db.scalars(select(EngineerModel).where(EngineerModel.email == ticket.assigned_to))
                ).first()
                if eng and eng.current_workload > 0:
                    eng.current_workload -= 1
            trace.append(
                {
                    "id": "close_ticket",
                    "title": "Close Ticket",
                    "status": "completed",
                    "detail": f"{ticket.number} → Closed",
                }
            )
        else:
            trace.append(
                {
                    "id": "close_ticket",
                    "title": "Close Ticket",
                    "status": "skipped",
                    "detail": "AI Verify failed or auto_close=false — left Resolved for engineer review",
                }
            )

        # 6. Store Embedding
        content = (
            f"Incident {ticket.number}\n"
            f"Category: {ticket.category}/{ticket.subcategory}\n"
            f"Priority: {ticket.priority}\n"
            f"Problem: {ticket.short_description}\n{ticket.description}\n"
            f"Root cause: {ticket.root_cause_suggestion}\n"
            f"Resolution notes:\n"
            + "\n".join(str(n.get("body") or "") for n in (ticket.work_notes or [])[-6:])
        )
        embedding = embed_text(content)
        doc_id = f"resolved-{ticket.id}"
        vector_store.index_document(
            title=f"Resolved {ticket.number}: {ticket.short_description}",
            content=content,
            source="learned_incident",
            doc_id=doc_id,
            extra={"number": ticket.number, "ticket_id": ticket.id},
        )
        ticket.embeddings = embedding
        trace.append(
            {
                "id": "store_embedding",
                "title": "Store Embedding",
                "status": "completed",
                "detail": f"doc_id={doc_id} dim={len(embedding)}",
            }
        )

        # Update status lifecycle marks in workflow_trace
        meta = dict(ticket.ticket_metadata or {})
        wf_trace = list(meta.get("workflow_trace") or [])
        current_idx = STATUS_ORDER.index(ticket.state) if ticket.state in STATUS_ORDER else -1
        for step in wf_trace:
            if step.get("kind") == "status" and step.get("title") in STATUS_ORDER:
                idx = STATUS_ORDER.index(step["title"])
                if idx <= current_idx:
                    step["status"] = "completed"
        meta["resolution_workflow"] = {
            "run_id": run_id,
            "engineer": engineer,
            "ai_verify": verify,
            "closed": closed,
            "embedding_doc_id": doc_id,
            "trace": trace,
            "completed_at": now.isoformat(),
        }
        meta["learned_at"] = now.isoformat()
        meta["learned_by"] = engineer
        meta["workflow_trace"] = wf_trace
        ticket.ticket_metadata = meta
        ticket.updated_at = now
        await db.commit()
        await db.refresh(ticket)

        await n8n_client.forward_webhook(
            {
                "event": "ticket.resolve",
                "run_id": run_id,
                "ticket": ticket.number,
                "verified": verify["verified"],
                "closed": closed,
            }
        )

        from app.application.use_cases.ticket_service import _serialize_ticket

        result = {
            "workflow": RESOLUTION_WORKFLOW,
            "run_id": run_id,
            "ticket": _serialize_ticket(ticket),
            "ai_verify": verify,
            "closed": closed,
            "embedding_doc_id": doc_id,
            "customer_email": {"to": customer, "result": email_result},
            "trace": trace,
        }
        _RUN_LOGS.append({**result, "created_at": now.isoformat(), "ticket": ticket.number})
        if len(_RUN_LOGS) > 200:
            del _RUN_LOGS[: len(_RUN_LOGS) - 200]
        logger.info(
            "Resolution workflow %s for %s verified=%s closed=%s",
            run_id,
            ticket.number,
            verify["verified"],
            closed,
        )
        return result


resolution_workflow = ResolutionWorkflow()
