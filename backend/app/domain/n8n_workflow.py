"""Canonical n8n Ticket Created workflow."""

from __future__ import annotations

N8N_TICKET_CREATED_WORKFLOW = {
    "name": "n8n Workflow",
    "trigger": "Ticket Created",
    "event": "ticket.created",
    "steps": [
        {"id": "webhook", "title": "Ticket Created : Webhook", "type": "trigger"},
        {"id": "ai_classification", "title": "AI Classification", "type": "ai"},
        {"id": "priority", "title": "Priority", "type": "ai"},
        {"id": "assignment", "title": "Assignment", "type": "ai"},
        {"id": "servicenow_api", "title": "ServiceNow API", "type": "integration"},
        {"id": "email", "title": "Email", "type": "notify"},
        {"id": "slack", "title": "Slack", "type": "notify"},
        {"id": "log_database", "title": "Log Database", "type": "persist"},
    ],
}
