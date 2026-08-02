"""Canonical Resolution Workflow."""

from __future__ import annotations

RESOLUTION_WORKFLOW = {
    "name": "Resolution Workflow",
    "trigger": "Engineer",
    "event": "ticket.resolve",
    "steps": [
        {"id": "engineer", "title": "Engineer", "type": "actor"},
        {"id": "resolve_ticket", "title": "Resolve Ticket", "type": "action"},
        {"id": "ai_verify", "title": "AI Verify", "type": "ai"},
        {"id": "customer_email", "title": "Customer Email", "type": "notify"},
        {"id": "close_ticket", "title": "Close Ticket", "type": "action"},
        {"id": "store_embedding", "title": "Store Embedding", "type": "persist"},
    ],
}
