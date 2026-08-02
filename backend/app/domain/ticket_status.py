"""Canonical ticket status lifecycle."""

from __future__ import annotations

from app.domain.value_objects.ticket_state import TicketState

TICKET_STATUS_LIFECYCLE = {
    "name": "Ticket Status",
    "steps": [
        {"id": "new", "code": "NEW", "title": TicketState.NEW.value},
        {"id": "assigned", "code": "ASSIGNED", "title": TicketState.ASSIGNED.value},
        {
            "id": "work_in_progress",
            "code": "WORK_IN_PROGRESS",
            "title": TicketState.WORK_IN_PROGRESS.value,
        },
        {
            "id": "waiting_for_customer",
            "code": "WAITING_FOR_CUSTOMER",
            "title": TicketState.WAITING_FOR_CUSTOMER.value,
        },
        {"id": "resolved", "code": "RESOLVED", "title": TicketState.RESOLVED.value},
        {"id": "completed", "code": "COMPLETED", "title": TicketState.COMPLETED.value},
        {"id": "closed", "code": "CLOSED", "title": TicketState.CLOSED.value},
    ],
}

STATUS_ORDER = [s["title"] for s in TICKET_STATUS_LIFECYCLE["steps"]]

# Linear forward transitions (plus same-state no-op handled by caller)
ALLOWED_TRANSITIONS: dict[str, list[str]] = {
    TicketState.NEW.value: [
        TicketState.ASSIGNED.value,
        TicketState.WORK_IN_PROGRESS.value,
        TicketState.WAITING_FOR_CUSTOMER.value,
        TicketState.RESOLVED.value,
        TicketState.COMPLETED.value,
        TicketState.CLOSED.value,
    ],
    TicketState.ASSIGNED.value: [
        TicketState.WORK_IN_PROGRESS.value,
        TicketState.WAITING_FOR_CUSTOMER.value,
        TicketState.RESOLVED.value,
        TicketState.COMPLETED.value,
        TicketState.CLOSED.value,
    ],
    TicketState.WORK_IN_PROGRESS.value: [
        TicketState.WAITING_FOR_CUSTOMER.value,
        TicketState.RESOLVED.value,
        TicketState.COMPLETED.value,
        TicketState.CLOSED.value,
        TicketState.ASSIGNED.value,  # reassign / reopen within active work
    ],
    TicketState.WAITING_FOR_CUSTOMER.value: [
        TicketState.WORK_IN_PROGRESS.value,
        TicketState.RESOLVED.value,
        TicketState.COMPLETED.value,
        TicketState.CLOSED.value,
    ],
    TicketState.RESOLVED.value: [
        TicketState.COMPLETED.value,
        TicketState.CLOSED.value,
        TicketState.WORK_IN_PROGRESS.value,  # reopen
    ],
    TicketState.COMPLETED.value: [
        TicketState.CLOSED.value,
        TicketState.WORK_IN_PROGRESS.value,  # reopen
    ],
    TicketState.CLOSED.value: [
        TicketState.WORK_IN_PROGRESS.value,  # reopen
    ],
}


def can_transition(from_state: str, to_state: str) -> bool:
    if from_state == to_state:
        return True
    return to_state in ALLOWED_TRANSITIONS.get(from_state, [])
