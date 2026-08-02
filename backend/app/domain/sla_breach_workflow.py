"""Canonical SLA Breach cron workflow."""

from __future__ import annotations

SLA_BREACH_WORKFLOW = {
    "name": "SLA Breach",
    "trigger": "Cron",
    "event": "sla.breach",
    "steps": [
        {"id": "cron", "title": "Cron", "type": "trigger"},
        {"id": "find_expired_sla", "title": "Find Expired SLA", "type": "query"},
        {"id": "notify_manager", "title": "Notify Manager", "type": "notify"},
        {"id": "escalate", "title": "Escalate", "type": "action"},
        {"id": "create_rca_task", "title": "Create RCA Task", "type": "action"},
    ],
}
