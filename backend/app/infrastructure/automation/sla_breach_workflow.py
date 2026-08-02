"""
SLA Breach workflow:

Cron → Find Expired SLA → Notify Manager → Escalate → Create RCA Task
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.sub_agents import EscalationAgent, NotificationAgent
from app.core.config import get_settings
from app.domain.sla_breach_workflow import SLA_BREACH_WORKFLOW
from app.domain.value_objects.ticket_state import TicketState
from app.infrastructure.db.models import TicketModel
from app.infrastructure.monitoring.metrics_registry import inc_escalations
from app.infrastructure.n8n.client import n8n_client
from app.infrastructure.notifications.channels import notification_channels

logger = logging.getLogger(__name__)

_RUN_LOGS: list[dict[str, Any]] = []
MANAGER_EMAIL = "ops.manager@example.com"


class SLABreachWorkflow:
    def definition(self) -> dict[str, Any]:
        return SLA_BREACH_WORKFLOW

    def logs(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(reversed(_RUN_LOGS[-limit:]))

    async def run(self, db: AsyncSession) -> dict[str, Any]:
        settings = get_settings()
        now = datetime.now(timezone.utc)
        run_id = str(uuid4())
        trace: list[dict[str, Any]] = []

        # 1. Cron
        trace.append(
            {
                "id": "cron",
                "title": "Cron",
                "status": "completed",
                "detail": f"triggered_at={now.isoformat()}",
            }
        )

        # 2. Find Expired SLA
        open_states = {
            TicketState.NEW.value,
            TicketState.ASSIGNED.value,
            TicketState.WORK_IN_PROGRESS.value,
            TicketState.WAITING_FOR_CUSTOMER.value,
        }

        def _aware(dt: datetime | None) -> datetime | None:
            if dt is None:
                return None
            return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)

        tickets = list((await db.scalars(select(TicketModel))).all())
        expired: list[TicketModel] = []
        for ticket in tickets:
            due = _aware(ticket.sla_due_at)
            if ticket.state not in open_states or not due:
                continue
            if due < now:
                expired.append(ticket)

        trace.append(
            {
                "id": "find_expired_sla",
                "title": "Find Expired SLA",
                "status": "completed",
                "detail": f"{len(expired)} expired ticket(s)",
                "tickets": [t.number for t in expired],
            }
        )

        processed: list[dict[str, Any]] = []
        escalation_agent = EscalationAgent()

        for ticket in expired:
            item_trace: list[dict[str, Any]] = []
            meta = dict(ticket.ticket_metadata or {})

            # 3. Notify Manager
            message = (
                f"SLA BREACH: {ticket.number} '{ticket.short_description}' is past resolution due "
                f"({ticket.sla_due_at}). Priority {ticket.priority}. "
                f"Assignee: {ticket.assigned_to or 'Unassigned'}."
            )
            recipients = list(
                dict.fromkeys(
                    [r for r in [MANAGER_EMAIL, ticket.assigned_to, ticket.caller] if r]
                )
            )
            email_result = notification_channels.send_smtp(
                subject=f"[AIOps][SLA Breach] {ticket.number}",
                message=message,
                recipients=recipients,
            )
            slack_result = await notification_channels.send_slack(
                subject=f"SLA Breach {ticket.number}",
                message=message,
            )
            item_trace.append(
                {
                    "id": "notify_manager",
                    "title": "Notify Manager",
                    "status": "completed",
                    "detail": f"manager={MANAGER_EMAIL}",
                    "data": {"email": email_result, "slack": slack_result, "recipients": recipients},
                }
            )

            # 4. Escalate
            if meta.get("sla_breach_escalated"):
                esc_detail = "already escalated"
                old_priority = ticket.priority
                new_priority = ticket.priority
                esc_data: dict[str, Any] = {"skipped": True}
            else:
                result = escalation_agent.run(
                    {
                        "number": ticket.number,
                        "priority": ticket.priority,
                        "assigned_to": ticket.assigned_to,
                    }
                )
                old_priority = ticket.priority
                new_priority = result.data.get("to_priority", ticket.priority)
                ticket.priority = new_priority
                hours = {
                    "P1": settings.sla_p1_hours,
                    "P2": settings.sla_p2_hours,
                    "P3": settings.sla_p3_hours,
                }.get(new_priority, 2.0)
                ticket.sla_due_at = now + timedelta(hours=max(hours / 2, 1.0))
                ticket.sla_breached = True
                meta["sla_breach_escalated"] = True
                meta["escalated"] = True
                esc_data = result.data
                esc_detail = f"{old_priority} → {new_priority}"
                notes = list(ticket.work_notes or [])
                notes.append(
                    {
                        "id": str(uuid4()),
                        "author": "sla-breach-cron",
                        "body": f"**SLA Breach Escalate**\n\n{result.data.get('message', esc_detail)}",
                        "format": "markdown",
                        "created_at": now.isoformat(),
                        "is_internal": True,
                    }
                )
                ticket.work_notes = notes
                logs = list(ticket.audit_logs or [])
                logs.append(
                    {
                        "id": str(uuid4()),
                        "actor": "sla-breach-cron",
                        "action": "escalate",
                        "details": {"from": old_priority, "to": new_priority, "reason": "sla_expired"},
                        "created_at": now.isoformat(),
                    }
                )
                ticket.audit_logs = logs

            item_trace.append(
                {
                    "id": "escalate",
                    "title": "Escalate",
                    "status": "completed",
                    "detail": esc_detail,
                    "data": esc_data,
                }
            )

            # 5. Create RCA Task
            rca_task = meta.get("rca_task")
            if not rca_task:
                rca_task = {
                    "id": str(uuid4()),
                    "type": "RCA",
                    "title": f"RCA: {ticket.number} — {ticket.short_description}",
                    "status": "Open",
                    "parent_ticket": ticket.number,
                    "priority": new_priority,
                    "assigned_to": MANAGER_EMAIL,
                    "created_at": now.isoformat(),
                    "description": (
                        f"Root cause analysis task created after SLA breach for {ticket.number}. "
                        f"Investigate why resolution exceeded SLA and document preventive actions. "
                        f"Suggested RCA focus: {ticket.root_cause_suggestion or 'pending analysis'}."
                    ),
                }
                meta["rca_task"] = rca_task
                notes = list(ticket.work_notes or [])
                notes.append(
                    {
                        "id": str(uuid4()),
                        "author": "sla-breach-cron",
                        "body": (
                            f"**RCA Task Created**\n\n"
                            f"- id: `{rca_task['id']}`\n"
                            f"- title: {rca_task['title']}\n"
                            f"- assigned_to: {rca_task['assigned_to']}\n"
                            f"- status: {rca_task['status']}"
                        ),
                        "format": "markdown",
                        "created_at": now.isoformat(),
                        "is_internal": True,
                    }
                )
                ticket.work_notes = notes
                rca_detail = f"created {rca_task['id']}"
            else:
                rca_detail = f"existing {rca_task.get('id')}"

            item_trace.append(
                {
                    "id": "create_rca_task",
                    "title": "Create RCA Task",
                    "status": "completed",
                    "detail": rca_detail,
                    "data": rca_task,
                }
            )

            meta["sla_breach_workflow"] = {
                "run_id": run_id,
                "processed_at": now.isoformat(),
                "trace": item_trace,
            }
            ticket.ticket_metadata = meta
            ticket.updated_at = now

            processed.append(
                {
                    "number": ticket.number,
                    "id": ticket.id,
                    "from_priority": old_priority,
                    "to_priority": new_priority,
                    "rca_task_id": rca_task.get("id"),
                    "manager_notified": MANAGER_EMAIL,
                    "trace": item_trace,
                }
            )

            await n8n_client.forward_webhook(
                {
                    "event": "sla.breach",
                    "ticket": ticket.number,
                    "rca_task": rca_task,
                    "from_priority": old_priority,
                    "to_priority": new_priority,
                }
            )

        await db.commit()
        if processed:
            inc_escalations(len(processed))

        result = {
            "workflow": SLA_BREACH_WORKFLOW,
            "run_id": run_id,
            "expired_count": len(expired),
            "processed_count": len(processed),
            "tickets": processed,
            "trace": trace
            + [
                {
                    "id": "notify_manager",
                    "title": "Notify Manager",
                    "status": "completed",
                    "detail": f"{len(processed)} manager notification(s)",
                },
                {
                    "id": "escalate",
                    "title": "Escalate",
                    "status": "completed",
                    "detail": f"{len(processed)} escalation(s)",
                },
                {
                    "id": "create_rca_task",
                    "title": "Create RCA Task",
                    "status": "completed",
                    "detail": f"{sum(1 for p in processed if p.get('rca_task_id'))} RCA task(s)",
                },
            ],
        }
        _RUN_LOGS.append({**result, "created_at": now.isoformat()})
        if len(_RUN_LOGS) > 200:
            del _RUN_LOGS[: len(_RUN_LOGS) - 200]
        logger.info("SLA Breach cron processed %s expired ticket(s)", len(processed))
        return result


sla_breach_workflow = SLABreachWorkflow()
