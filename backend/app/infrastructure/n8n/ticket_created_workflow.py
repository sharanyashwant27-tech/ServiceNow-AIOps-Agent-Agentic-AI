"""
n8n Ticket Created workflow (executable in-process + webhook-forwardable):

Ticket Created : Webhook → AI Classification → Priority → Assignment →
ServiceNow API → Email → Slack → Log Database
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.agents.sub_agents import AssignmentAgent, ClassificationAgent, NotificationAgent, PriorityAgent
from app.domain.n8n_workflow import N8N_TICKET_CREATED_WORKFLOW
from app.infrastructure.notifications.channels import notification_channels
from app.infrastructure.servicenow.client import servicenow_client

logger = logging.getLogger(__name__)

# In-memory workflow execution log (demo "Log Database")
_WORKFLOW_LOGS: list[dict[str, Any]] = []


class TicketCreatedN8NWorkflow:
    def definition(self) -> dict[str, Any]:
        return N8N_TICKET_CREATED_WORKFLOW

    def logs(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(reversed(_WORKFLOW_LOGS[-limit:]))

    async def run(
        self,
        payload: dict[str, Any],
        *,
        engineers: list[dict[str, Any]] | None = None,
        sync_servicenow: bool = True,
    ) -> dict[str, Any]:
        trace: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc).isoformat()
        run_id = str(uuid4())

        # 1. Ticket Created : Webhook
        webhook_payload = {"event": "ticket.created", "received_at": now, "data": payload}
        trace.append(
            {
                "id": "webhook",
                "title": "Ticket Created : Webhook",
                "status": "completed",
                "detail": payload.get("number") or payload.get("id") or "received",
            }
        )

        short = payload.get("title") or payload.get("short_description") or ""
        description = payload.get("description") or short

        # 2. AI Classification
        classification = ClassificationAgent().run(short, description)
        category = classification.data.get("category")
        subcategory = classification.data.get("subcategory")
        trace.append(
            {
                "id": "ai_classification",
                "title": "AI Classification",
                "status": "completed",
                "detail": f"{category} / {subcategory}",
                "data": classification.data,
            }
        )

        # 3. Priority
        priority_result = PriorityAgent().run(short, description)
        priority = priority_result.data.get("priority", "P3")
        sla = priority_result.data.get("resolution_time", "6 Hours")
        trace.append(
            {
                "id": "priority",
                "title": "Priority",
                "status": "completed",
                "detail": f"{priority} · {sla}",
                "data": priority_result.data,
            }
        )

        # 4. Assignment
        skill = subcategory or category or "General"
        # Prefer pre-assigned team from payload when present (AI Ticket Creation)
        if payload.get("assignment_group") or payload.get("assigned_to"):
            assignment_data = {
                "assigned_to": payload.get("assigned_to"),
                "assigned_name": payload.get("assigned_name"),
                "assignment_group": payload.get("assignment_group") or payload.get("team") or "IT Support",
                "team": payload.get("assignment_group") or payload.get("team"),
            }
            assign_notes = f"Using ticket assignment {assignment_data['assignment_group']}"
        else:
            assign_result = AssignmentAgent().run(skill, engineers or [])
            assignment_data = assign_result.data
            assign_notes = assign_result.notes
        trace.append(
            {
                "id": "assignment",
                "title": "Assignment",
                "status": "completed",
                "detail": assign_notes,
                "data": assignment_data,
            }
        )

        # 5. ServiceNow API
        sn_payload = {
            **payload,
            "short_description": short,
            "description": description,
            "priority": priority,
            "category": category,
            "subcategory": subcategory,
            "assignment_group": assignment_data.get("assignment_group") or assignment_data.get("team"),
            "assigned_to": assignment_data.get("assigned_to"),
        }
        if sync_servicenow:
            sn = await servicenow_client.create_incident(sn_payload)
            sn_status = "completed"
            sn_detail = sn.get("sys_id") or sn.get("number") or "synced"
        else:
            sn = {"skipped": True}
            sn_status = "skipped"
            sn_detail = "sync_servicenow=false"
        trace.append(
            {
                "id": "servicenow_api",
                "title": "ServiceNow API",
                "status": sn_status,
                "detail": str(sn_detail),
                "data": sn,
            }
        )

        # 6. Email
        message = NotificationAgent.format_ticket_created(
            payload.get("number") or "PENDING",
            priority,
            assignment_data.get("assigned_name"),
            sla,
        )
        recipients = [r for r in [assignment_data.get("assigned_to"), payload.get("caller"), payload.get("created_by")] if r]
        if not recipients:
            recipients = ["ops@example.com"]
        email_result = notification_channels.send_smtp(
            subject=f"[AIOps][ticket.created] {payload.get('number') or short}",
            message=message,
            recipients=recipients,
        )
        trace.append(
            {
                "id": "email",
                "title": "Email",
                "status": "completed",
                "detail": f"to={', '.join(recipients)} sent={email_result.get('sent')} mocked={email_result.get('mocked', False)}",
                "data": {"recipients": recipients, "message": message, "result": email_result},
            }
        )

        # 7. Slack
        slack_result = await notification_channels.send_slack(
            subject=f"Ticket Created {payload.get('number') or ''}",
            message=message,
        )
        trace.append(
            {
                "id": "slack",
                "title": "Slack",
                "status": "completed",
                "detail": str(slack_result),
                "data": {"result": slack_result},
            }
        )

        # 8. Log Database
        log_row = {
            "id": run_id,
            "workflow": "ticket.created",
            "ticket_number": payload.get("number"),
            "category": category,
            "priority": priority,
            "assignment_group": assignment_data.get("assignment_group") or assignment_data.get("team"),
            "assigned_to": assignment_data.get("assigned_to"),
            "servicenow": sn,
            "created_at": now,
            "trace": trace,
            "webhook_payload": webhook_payload,
        }
        _WORKFLOW_LOGS.append(log_row)
        if len(_WORKFLOW_LOGS) > 500:
            del _WORKFLOW_LOGS[: len(_WORKFLOW_LOGS) - 500]
        trace.append(
            {
                "id": "log_database",
                "title": "Log Database",
                "status": "completed",
                "detail": f"run_id={run_id}",
            }
        )

        # Forward to external n8n if configured
        from app.infrastructure.n8n.client import n8n_client

        forward = await n8n_client.forward_webhook(
            {
                "workflow": N8N_TICKET_CREATED_WORKFLOW["name"],
                "event": "ticket.created",
                "run_id": run_id,
                "data": sn_payload,
                "trace": trace,
            }
        )

        return {
            "workflow": N8N_TICKET_CREATED_WORKFLOW,
            "run_id": run_id,
            "classification": classification.data,
            "priority": priority_result.data,
            "assignment": assignment_data,
            "servicenow": sn,
            "notifications": {"email": email_result, "slack": slack_result, "message": message},
            "log_id": run_id,
            "trace": trace,
            "n8n_forward": forward,
        }


ticket_created_n8n_workflow = TicketCreatedN8NWorkflow()
