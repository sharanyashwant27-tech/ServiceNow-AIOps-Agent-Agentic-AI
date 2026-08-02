from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dto.schemas import AgentRunResponse, TicketCreate
from app.application.use_cases.ticket_service import TicketService
from app.infrastructure.db.models import UserModel
from app.infrastructure.db.session import get_db
from app.interfaces.api.deps import get_current_user

router = APIRouter(prefix="/automation", tags=["automation"])


class AlertIngest(BaseModel):
    """Monitoring / ServiceNow / n8n alert payload → automatic ticket creation."""

    alert_name: str
    severity: str = Field(default="major", description="critical|major|minor")
    message: str
    source: str = "monitoring"
    configuration_item: str | None = None
    caller: str = "monitoring@example.com"


@router.post("/ingest-alert", response_model=AgentRunResponse)
async def ingest_alert(
    body: AlertIngest,
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(get_current_user),
) -> dict:
    """Automatically create + triage a ticket from an inbound alert."""
    severity_map = {
        "critical": "Production critical outage",
        "major": "Major service degradation",
        "minor": "Minor issue reported",
    }
    prefix = severity_map.get(body.severity.lower(), "Alert")
    short = f"[{body.source}] {body.alert_name}"
    description = (
        f"{prefix}.\n"
        f"Alert: {body.alert_name}\n"
        f"Severity: {body.severity}\n"
        f"Source: {body.source}\n"
        f"Details: {body.message}"
    )
    result = await TicketService(db).create_and_triage(
        short_description=short,
        description=description,
        caller=body.caller,
        configuration_item=body.configuration_item,
        sync_servicenow=False,
    )
    ticket = result["ticket"]
    # mark auto-created
    from app.infrastructure.db.models import TicketModel

    row = await db.get(TicketModel, ticket["id"])
    if row:
        meta = dict(row.ticket_metadata or {})
        meta["auto_created"] = True
        meta["alert_source"] = body.source
        row.ticket_metadata = meta
        await db.commit()
        await db.refresh(row)
        from app.application.use_cases.ticket_service import _serialize_ticket

        result["ticket"] = _serialize_ticket(row)
    return result


@router.post("/escalate-overdue")
async def escalate_overdue(
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(get_current_user),
) -> dict:
    """Escalate SLA-breached open tickets and notify engineers/managers."""
    return await TicketService(db).escalate_overdue()


@router.get("/sla-breach-workflow")
async def sla_breach_workflow_definition(_: UserModel = Depends(get_current_user)) -> dict:
    from app.domain.sla_breach_workflow import SLA_BREACH_WORKFLOW

    return SLA_BREACH_WORKFLOW


@router.get("/sla-breach-workflow/logs")
async def sla_breach_workflow_logs(_: UserModel = Depends(get_current_user)) -> dict:
    from app.infrastructure.automation.sla_breach_workflow import sla_breach_workflow

    return {"logs": sla_breach_workflow.logs()}


@router.post("/sla-breach-workflow/run")
async def run_sla_breach_workflow(
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(get_current_user),
) -> dict:
    """
    SLA Breach cron job:

    Cron → Find Expired SLA → Notify Manager → Escalate → Create RCA Task
    """
    from app.infrastructure.automation.sla_breach_workflow import sla_breach_workflow

    return await sla_breach_workflow.run(db)


@router.get("/resolution-workflow")
async def resolution_workflow_definition(_: UserModel = Depends(get_current_user)) -> dict:
    from app.domain.resolution_workflow import RESOLUTION_WORKFLOW

    return RESOLUTION_WORKFLOW


@router.get("/resolution-workflow/logs")
async def resolution_workflow_logs(_: UserModel = Depends(get_current_user)) -> dict:
    from app.infrastructure.automation.resolution_workflow import resolution_workflow

    return {"logs": resolution_workflow.logs()}


@router.get("/capabilities")
async def capabilities(_: UserModel = Depends(get_current_user)) -> dict:
    return {
        "capabilities": [
            {"id": "auto_create", "name": "Create tickets automatically", "endpoint": "POST /automation/ingest-alert"},
            {
                "id": "classify",
                "name": "Ticket Classification Agent",
                "agent": "ticket_classification",
                "detects": ["Incident", "Service Request", "Change Request", "Problem", "Security Issue"],
            },
            {"id": "duplicates", "name": "Detect duplicate incidents", "agent": "duplicate_detection"},
            {"id": "assign", "name": "Assign tickets automatically", "agent": "assignment"},
            {"id": "prioritize", "name": "Prioritize tickets (P1/P2/P3)", "agent": "priority"},
            {"id": "sla", "name": "Set SLA automatically", "agent": "sla_monitor", "targets": {"P1": "2h", "P2": "4h", "P3": "6h"}},
            {"id": "rag_resolve", "name": "Suggest resolutions using RAG", "agent": "resolution_suggestion"},
            {"id": "search", "name": "Search previous incidents", "endpoint": "GET /incidents/search"},
            {"id": "rca", "name": "Generate root cause analysis", "agent": "graphrag"},
            {"id": "escalate", "name": "Escalate overdue incidents", "endpoint": "POST /automation/escalate-overdue"},
            {
                "id": "sla_breach",
                "name": "SLA Breach cron",
                "endpoint": "POST /automation/sla-breach-workflow/run",
                "flow": "Cron → Find Expired SLA → Notify Manager → Escalate → Create RCA Task",
            },
            {
                "id": "resolution",
                "name": "Resolution Workflow",
                "endpoint": "POST /tickets/{id}/resolution-workflow",
                "flow": "Engineer → Resolve → AI Verify → Customer Email → Close → Store Embedding",
            },
            {"id": "notify", "name": "Notify engineers", "agent": "notification"},
            {"id": "dashboards", "name": "Generate management dashboards", "endpoint": "GET /dashboard"},
            {"id": "learn", "name": "Learn from previous tickets", "trigger": "on Resolved/Completed/Closed"},
        ]
    }


@router.post("/create-ticket", response_model=AgentRunResponse)
async def auto_create_ticket(
    body: TicketCreate,
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(get_current_user),
) -> dict:
    """Convenience alias for automated ticket creation + full agent triage."""
    return await TicketService(db).create_and_triage(
        short_description=body.short_description,
        description=body.description,
        caller=body.caller,
        configuration_item=body.configuration_item,
        sync_servicenow=body.sync_servicenow,
    )
