from enum import Enum


class TicketState(str, Enum):
    NEW = "New"
    ASSIGNED = "Assigned"
    WORK_IN_PROGRESS = "Work In Progress"
    WAITING_FOR_CUSTOMER = "Waiting for Customer"
    RESOLVED = "Resolved"
    COMPLETED = "Completed"
    CLOSED = "Closed"


class Priority(str, Enum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"

    @property
    def sla_hours(self) -> float:
        return {"P1": 2.0, "P2": 4.0, "P3": 6.0}[self.value]
