from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.ticket_service import TicketService
from app.core.config import get_settings
from app.infrastructure.db.models import UserModel
from app.infrastructure.db.session import get_db
from app.infrastructure.llm.provider import llm_provider
from app.infrastructure.notifications.channels import notification_channels
from app.infrastructure.ocr.tesseract_ocr import tesseract_ocr
from app.infrastructure.rag.langchain_rag import langchain_rag
from app.interfaces.api.deps import get_current_user

router = APIRouter(prefix="/stack", tags=["stack"])


@router.get("/architecture")
async def architecture(_: UserModel = Depends(get_current_user)) -> dict:
    from app.domain.architecture import ARCHITECTURE

    return ARCHITECTURE


@router.get("/ticket-workflow")
async def ticket_workflow(_: UserModel = Depends(get_current_user)) -> dict:
    from app.domain.ticket_workflow import TICKET_WORKFLOW

    return TICKET_WORKFLOW


@router.get("/ticket-status")
async def ticket_status(_: UserModel = Depends(get_current_user)) -> dict:
    from app.domain.ticket_status import TICKET_STATUS_LIFECYCLE

    return TICKET_STATUS_LIFECYCLE


@router.get("/notes-viewer")
async def notes_viewer_capabilities(_: UserModel = Depends(get_current_user)) -> dict:
    from app.domain.activity_notes import NOTES_VIEWER_SUPPORTS

    return {"name": "Notes Viewer", "supports": NOTES_VIEWER_SUPPORTS}


@router.get("/ticket-entity")
async def ticket_entity(_: UserModel = Depends(get_current_user)) -> dict:
    from app.domain.entities.ticket import TICKET_ENTITY_FIELDS

    return {
        "name": "Ticket",
        "fields": TICKET_ENTITY_FIELDS,
        "mapping": {
            "id": "uuid",
            "title": "short_description",
            "description": "description",
            "priority": "P1|P2|P3",
            "status": "NEW→…→CLOSED lifecycle",
            "category": "Incident type / domain",
            "subcategory": "Network|Database|…",
            "assigned_to": "engineer email",
            "assignment_group": "assignment group / team",
            "created_by": "caller",
            "created_date": "created_at",
            "completed_date": "closed_at or resolved_at",
            "resolution_due": "sla_due_at",
            "work_notes": "activity notes source",
            "attachments": "files/images",
            "sla": "{due_at, breached, hours, resolution_time}",
            "embeddings": "vector for duplicate/RAG",
            "knowledge_links": "KB / runbook references",
            "related_incidents": "duplicate + similar tickets",
        },
    }


@router.post("/agents/classify")
async def classify_ticket(
    short_description: str,
    description: str = "",
    _: UserModel = Depends(get_current_user),
) -> dict:
    """Sub Agent 1 — Ticket Classification Agent demo endpoint."""
    from app.agents.sub_agents import ClassificationAgent

    result = ClassificationAgent().run(short_description, description)
    return {
        "agent": "Sub Agent 1 — Ticket Classification Agent",
        "input": short_description,
        "output": {
            "category": result.data.get("category"),
            "subcategory": result.data.get("subcategory"),
            "confidence": f"{result.data.get('confidence_pct')}%",
        },
        "confidence": result.confidence,
        "details": result.data,
        "notes": result.notes,
    }


@router.post("/agents/priority")
async def priority_agent(short_description: str, description: str = "", _: UserModel = Depends(get_current_user)) -> dict:
    from app.agents.sub_agents import PriorityAgent

    result = PriorityAgent().run(short_description, description)
    return {
        "agent": "Sub Agent 2 — Priority Agent",
        "input": short_description,
        "output": {
            "priority": result.data.get("priority"),
            "label": result.data.get("label"),
            "resolution_time": result.data.get("resolution_time"),
        },
        "details": result.data,
        "notes": result.notes,
    }


@router.post("/agents/assign")
async def assignment_agent(
    skill_domain: str = "Network",
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(get_current_user),
) -> dict:
    from sqlalchemy import select

    from app.agents.sub_agents import AssignmentAgent
    from app.infrastructure.db.models import EngineerModel

    engineers = list((await db.scalars(select(EngineerModel).where(EngineerModel.active.is_(True)))).all())
    payload = [
        {
            "name": e.name,
            "email": e.email,
            "skills": e.skills,
            "assignment_group": e.assignment_group,
            "team": e.assignment_group,
            "max_workload": e.max_workload,
            "current_workload": e.current_workload,
            "active": e.active,
            "available": True,
            "shift": "Day",
            "experience_years": 8 if e.name.lower() == "john" else 4,
        }
        for e in engineers
    ]
    result = AssignmentAgent().run(skill_domain, payload)
    return {
        "agent": "Sub Agent 3 — Assignment Agent",
        "input": skill_domain,
        "output": {
            "assign": result.data.get("assigned_name"),
            "team": result.data.get("team"),
            "email": result.data.get("assigned_to"),
        },
        "details": result.data,
        "notes": result.notes,
    }


@router.post("/agents/duplicate")
async def duplicate_agent(
    short_description: str,
    description: str = "",
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(get_current_user),
) -> dict:
    from sqlalchemy import select

    from app.agents.sub_agents import DuplicateDetectionAgent
    from app.infrastructure.db.models import TicketModel

    existing = list((await db.scalars(select(TicketModel).limit(100))).all())
    candidates = [
        {"id": t.id, "number": t.number, "short_description": t.short_description, "description": t.description}
        for t in existing
    ]
    result = DuplicateDetectionAgent().run(short_description, description, candidates)
    return {"agent": "Sub Agent 4 — Duplicate Detection Agent", "input": short_description, "output": result.data, "notes": result.notes}


@router.post("/agents/resolution")
async def resolution_agent(query: str, _: UserModel = Depends(get_current_user)) -> dict:
    from app.agents.sub_agents import ResolutionAgent

    result = ResolutionAgent().run(query)
    return {
        "agent": "Sub Agent 5 — Resolution Agent (RAG)",
        "input": query,
        "output": {
            "suggested_resolution": result.data.get("suggested_resolution"),
            "confidence": f"{result.data.get('confidence_pct')}%",
            "references": result.data.get("references"),
        },
        "details": result.data,
        "notes": result.notes,
    }


@router.post("/agents/graphrag")
async def graphrag_agent(ci: str = "Storage-D", description: str = "", _: UserModel = Depends(get_current_user)) -> dict:
    from app.agents.sub_agents import GraphRAGAgent

    result = GraphRAGAgent().run(ci, description or f"{ci} failure")
    return {
        "agent": "Sub Agent 6 — GraphRAG Agent",
        "input": ci,
        "output": {
            "impact_chain": result.data.get("impact_chain"),
            "affected_services": result.data.get("affected_services"),
            "prediction": result.data.get("root_cause_suggestion"),
        },
        "details": result.data,
        "notes": result.notes,
    }


@router.get("/graphrag-pipeline")
async def graphrag_pipeline_definition(_: UserModel = Depends(get_current_user)) -> dict:
    from app.domain.graphrag_pipeline import GRAPHRAG_PIPELINE

    return GRAPHRAG_PIPELINE


@router.get("/n8n-workflow")
async def n8n_workflow_definition(_: UserModel = Depends(get_current_user)) -> dict:
    from app.domain.n8n_workflow import N8N_TICKET_CREATED_WORKFLOW

    return N8N_TICKET_CREATED_WORKFLOW


@router.get("/n8n-workflow/logs")
async def n8n_workflow_logs(_: UserModel = Depends(get_current_user)) -> dict:
    from app.infrastructure.n8n.ticket_created_workflow import ticket_created_n8n_workflow

    return {"logs": ticket_created_n8n_workflow.logs()}


@router.post("/n8n-workflow/ticket-created")
async def n8n_ticket_created_run(
    short_description: str = "Outlook is not opening",
    description: str = "",
    number: str = "INC-DEMO",
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(get_current_user),
) -> dict:
    """Demo-run the n8n Ticket Created workflow chain."""
    from sqlalchemy import select

    from app.infrastructure.db.models import EngineerModel
    from app.infrastructure.n8n.ticket_created_workflow import ticket_created_n8n_workflow

    engineers = list((await db.scalars(select(EngineerModel).where(EngineerModel.active.is_(True)))).all())
    eng_payload = [
        {
            "name": e.name,
            "email": e.email,
            "skills": e.skills,
            "assignment_group": e.assignment_group,
            "team": e.assignment_group,
            "active": e.active,
            "available": True,
            "current_workload": e.current_workload,
            "max_workload": e.max_workload,
            "experience_years": 5,
        }
        for e in engineers
    ]
    return await ticket_created_n8n_workflow.run(
        {
            "number": number,
            "title": short_description,
            "short_description": short_description,
            "description": description or short_description,
            "caller": "admin@example.com",
            "engineers": eng_payload,
            "sync_servicenow": True,
        },
        engineers=eng_payload,
        sync_servicenow=True,
    )


@router.post("/graphrag/pipeline")
async def graphrag_pipeline_run(
    ci: str = "Storage-D",
    description: str = "",
    title: str = "",
    number: str = "",
    _: UserModel = Depends(get_current_user),
) -> dict:
    """Execute GraphRAG Pipeline: Ticket → Neo4j → CI → Dependencies → Failures → RCA → Impact."""
    from app.infrastructure.graph.pipeline import graphrag_pipeline

    ticket = {
        "number": number or None,
        "title": title or f"{ci} failure",
        "description": description or f"{ci} failure",
        "configuration_item": ci,
    }
    return graphrag_pipeline.run(ticket=ticket, ci=ci, description=description)


@router.post("/agents/sla")
async def sla_agent(priority: str = "P1", _: UserModel = Depends(get_current_user)) -> dict:
    from app.agents.sub_agents import SLAAgent

    result = SLAAgent().run(priority)
    return {
        "agent": "Sub Agent 7 — SLA Agent",
        "input": priority,
        "output": {
            "resolution_time": result.data.get("resolution_time"),
            "sla_due_at": result.data.get("sla_due_at"),
            "escalate_before_breach_minutes": result.data.get("escalate_before_breach_minutes"),
            "should_escalate": result.data.get("should_escalate"),
            "risk": result.data.get("risk"),
        },
        "details": result.data,
        "notes": result.notes,
    }


@router.post("/agents/notify")
async def notification_agent(
    ticket_number: str = "INC100001",
    priority: str = "P1",
    assigned_name: str = "John",
    eta: str = "2 Hours",
    _: UserModel = Depends(get_current_user),
) -> dict:
    from app.agents.sub_agents import NotificationAgent

    message = NotificationAgent.format_ticket_created(ticket_number, priority, assigned_name, eta)
    result = NotificationAgent().run(ticket_number, "ticket_created", ["john@example.com"], message)
    return {
        "agent": "Sub Agent 8 — Notification Agent",
        "output": {
            "channels": ["Email", "Slack", "Teams", "SMS"],
            "message": message,
        },
        "details": result.data,
        "notes": result.notes,
    }


@router.get("/tech")
async def tech_stack(_: UserModel = Depends(get_current_user)) -> dict:
    s = get_settings()
    return {
        "components": [
            {"component": "Backend", "technology": "Python (FastAPI)", "status": "active"},
            {"component": "Frontend", "technology": "React.js", "status": "active"},
            {"component": "Database", "technology": "PostgreSQL", "configured": "postgresql" in s.database_url, "fallback": "SQLite"},
            {"component": "Cache", "technology": "Redis", "url": s.redis_url},
            {"component": "Vector Database", "technology": "Qdrant / Milvus / Pinecone", "backend": s.vector_backend},
            {"component": "Graph Database", "technology": "Neo4j", "uri": s.neo4j_uri},
            {"component": "LLM", "technology": "GPT / Llama 3 / Claude", "provider": s.llm_provider, "model": s.llm_model},
            {"component": "Workflow", "technology": "n8n", "configured": bool(s.n8n_webhook_url)},
            {"component": "RAG", "technology": "LangChain", "status": "active"},
            {"component": "GraphRAG", "technology": "Neo4j + LangGraph", "status": "active"},
            {"component": "AI Framework", "technology": "LangGraph", "status": "active"},
            {"component": "Agent Framework", "technology": "CrewAI / AutoGen", "selected": s.agent_framework},
            {"component": "Authentication", "technology": "JWT", "status": "active"},
            {"component": "OCR", "technology": "Tesseract", "enabled": s.ocr_enabled},
            {"component": "Email", "technology": "SMTP", "configured": bool(s.smtp_host)},
            {
                "component": "Notifications",
                "technology": "Email | Slack | Teams | SMS",
                "smtp": bool(s.smtp_host),
                "slack": bool(s.slack_webhook_url),
                "teams": bool(s.teams_webhook_url),
                "sms": bool(s.sms_webhook_url),
            },
            {"component": "ServiceNow Integration", "technology": "REST API", "configured": bool(s.servicenow_instance_url)},
            {"component": "Monitoring", "technology": "Prometheus + Grafana", "metrics": "/metrics"},
            {"component": "Deployment", "technology": "Docker + Kubernetes", "status": "manifests_present"},
        ]
    }


@router.get("/rag-pipeline")
async def rag_pipeline_definition(_: UserModel = Depends(get_current_user)) -> dict:
    from app.domain.rag_pipeline import RAG_PIPELINE

    return RAG_PIPELINE


@router.post("/rag/query")
async def rag_query(q: str, _: UserModel = Depends(get_current_user)) -> dict:
    from app.infrastructure.monitoring.metrics_registry import inc_rag_queries
    from app.infrastructure.rag.pipeline import rag_pipeline

    result = await rag_pipeline.run(q)
    inc_rag_queries()
    return result


@router.post("/rag/pipeline")
async def rag_pipeline_run(q: str, _: UserModel = Depends(get_current_user)) -> dict:
    """Execute the full RAG Pipeline and return step trace + Final Resolution."""
    from app.infrastructure.monitoring.metrics_registry import inc_rag_queries
    from app.infrastructure.rag.pipeline import rag_pipeline

    result = await rag_pipeline.run(q)
    inc_rag_queries()
    return result


@router.post("/llm/complete")
async def llm_complete(prompt: str, _: UserModel = Depends(get_current_user)) -> dict:
    return await llm_provider.complete(prompt)


@router.post("/ocr")
async def ocr_upload(
    file: UploadFile = File(...),
    _: UserModel = Depends(get_current_user),
) -> dict:
    content = await file.read()
    result = tesseract_ocr.extract_text(content, filename=file.filename or "", content_type=file.content_type or "")
    return {"filename": file.filename, **result}


@router.post("/notify/test")
async def notify_test(
    message: str = "ServiceNow AIOps notification test",
    user: UserModel = Depends(get_current_user),
) -> dict:
    return await notification_channels.send_all(
        subject="AIOps Notification Test",
        message=message,
        recipients=[user.email],
    )


@router.post("/triage/crew")
async def triage_with_crew(
    short_description: str,
    description: str,
    configuration_item: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: UserModel = Depends(get_current_user),
) -> dict:
    from app.agents.crew_orchestrator import crew_orchestrator

    # Use crew facade for orchestration metadata, persist via ticket service.
    preview = crew_orchestrator.run(
        {
            "short_description": short_description,
            "description": description,
            "configuration_item": configuration_item,
            "caller": user.email,
            "engineers": [],
            "existing_tickets": [],
            "ticket_number": "PREVIEW",
        }
    )
    created = await TicketService(db).create_and_triage(
        short_description=short_description,
        description=description,
        caller=user.email,
        configuration_item=configuration_item,
    )
    created["agent_framework"] = preview.get("agent_framework")
    created["crew_roles"] = preview.get("crew_roles")
    return created
