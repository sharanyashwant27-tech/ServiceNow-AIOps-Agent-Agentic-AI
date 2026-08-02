"""Canonical ticket workflow for the ServiceNow Agentic AIOps platform."""

from __future__ import annotations

TICKET_WORKFLOW = {
    "name": "Ticket Workflow",
    "steps": [
        {"id": "user", "title": "User", "type": "actor"},
        {"id": "raise_ticket", "title": "Raise Ticket", "type": "action"},
        {"id": "master_agent", "title": "Master Agent", "type": "orchestrator"},
        {"id": "classification", "title": "Classification Agent", "type": "agent"},
        {"id": "priority", "title": "Priority Agent", "type": "agent"},
        {"id": "duplicate_check", "title": "Duplicate Check", "type": "agent"},
        {"id": "assignment", "title": "Assignment Agent", "type": "agent"},
        {"id": "knowledge_search", "title": "Knowledge Search", "type": "agent"},
        {"id": "graphrag", "title": "GraphRAG Analysis", "type": "agent"},
        {"id": "create_servicenow", "title": "Create ServiceNow Ticket", "type": "integration"},
        {"id": "notify_engineer", "title": "Notify Engineer", "type": "agent"},
        {"id": "status_lifecycle", "title": "Ticket Status Lifecycle", "type": "state"},
    ],
    "lifecycle_states_after_create": [
        "New",
        "Assigned",
        "Work In Progress",
        "Waiting for Customer",
        "Resolved",
        "Completed",
        "Closed",
    ],
}
