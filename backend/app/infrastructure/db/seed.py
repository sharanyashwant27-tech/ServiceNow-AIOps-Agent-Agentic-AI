from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.infrastructure.db.models import EngineerModel, KnowledgeDocModel, UserModel
from app.infrastructure.vector.qdrant_store import vector_store


async def reindex_knowledge(db: AsyncSession) -> None:
    docs = (await db.scalars(select(KnowledgeDocModel))).all()
    for doc in docs:
        vector_store.index_document(doc.title, doc.content, source=doc.source, doc_id=doc.id)


async def seed_if_empty(db: AsyncSession) -> None:
    existing = (await db.scalars(select(UserModel).limit(1))).first()
    if existing:
        return

    admin = UserModel(
        id=str(uuid4()),
        email="admin@example.com",
        full_name="Platform Admin",
        hashed_password=hash_password("admin123"),
        role="admin",
    )
    engineer_user = UserModel(
        id=str(uuid4()),
        email="engineer@example.com",
        full_name="On-Call Engineer",
        hashed_password=hash_password("engineer123"),
        role="engineer",
    )
    db.add_all([admin, engineer_user])

    engineers = [
        EngineerModel(
            id=str(uuid4()),
            name="John",
            email="john@example.com",
            skills=["Network", "Infrastructure", "VPN", "Firewall", "DNS"],
            assignment_group="Infrastructure",
            max_workload=8,
            current_workload=1,
        ),
        EngineerModel(
            id=str(uuid4()),
            name="Ava Network",
            email="ava.network@example.com",
            skills=["Network", "VPN", "Firewall", "DNS"],
            assignment_group="Network Ops",
            max_workload=6,
            current_workload=1,
        ),
        EngineerModel(
            id=str(uuid4()),
            name="Ben Database",
            email="ben.db@example.com",
            skills=["Database", "Oracle", "Postgres", "SQL"],
            assignment_group="DBA Team",
            max_workload=5,
            current_workload=2,
        ),
        EngineerModel(
            id=str(uuid4()),
            name="Chloe Apps",
            email="chloe.apps@example.com",
            skills=["Application", "API", "Java", "Python"],
            assignment_group="App Support",
            max_workload=8,
            current_workload=3,
        ),
        EngineerModel(
            id=str(uuid4()),
            name="Diego Infra",
            email="diego.infra@example.com",
            skills=["Infrastructure", "Kubernetes", "Linux", "Cloud"],
            assignment_group="Platform",
            max_workload=7,
            current_workload=1,
        ),
        EngineerModel(
            id=str(uuid4()),
            name="Elena Security",
            email="elena.sec@example.com",
            skills=["Security", "IAM", "SOC", "Auth"],
            assignment_group="SecOps",
            max_workload=5,
            current_workload=0,
        ),
        EngineerModel(
            id=str(uuid4()),
            name="Sam Desktop",
            email="sam.desktop@example.com",
            skills=["Outlook", "Desktop", "Endpoint", "Software", "Windows"],
            assignment_group="Desktop Team",
            max_workload=8,
            current_workload=1,
        ),
    ]
    db.add_all(engineers)

    docs = [
        KnowledgeDocModel(
            id="KB-2025-889",
            title="KB-2025-889 Outlook Cache Reset",
            content=(
                "Restart Outlook Cache: close Outlook, clear OST cache / run /resetnavpane, "
                "repair Office click-to-run, reopen Outlook. Common after Windows or Office updates "
                "when Outlook will not open."
            ),
            source="kb",
            tags=["outlook", "software", "desktop", "KB-2025-889"],
        ),
        KnowledgeDocModel(
            id=str(uuid4()),
            title="VPN Concentrator High CPU Runbook",
            content=(
                "If VPN-CONCENTRATOR shows high CPU, check NETWORK-CORE saturation, "
                "drain connections, restart IKE services, and validate dependent gateways."
            ),
            source="kb",
            tags=["network", "vpn"],
        ),
        KnowledgeDocModel(
            id=str(uuid4()),
            title="Oracle Deadlock Triage",
            content=(
                "For DB-ORACLE-01 deadlocks impacting SAP-ERP, capture ASH reports, "
                "identify blocking sessions, and bounce application connection pools."
            ),
            source="kb",
            tags=["database", "oracle"],
        ),
        KnowledgeDocModel(
            id=str(uuid4()),
            title="API Gateway 5xx Surge",
            content=(
                "When API-GATEWAY returns elevated 5xx, inspect K8S-CLUSTER pod restarts, "
                "HPA events, and CRM-CLOUD upstream latency."
            ),
            source="kb",
            tags=["application", "api"],
        ),
        KnowledgeDocModel(
            id=str(uuid4()),
            title="Payment Service Latency",
            content=(
                "PAYMENT-SVC latency often correlates with DB-POSTGRES-02 IO wait. "
                "Check slow queries and API-GATEWAY retry storms."
            ),
            source="incident",
            tags=["payment", "database"],
        ),
        KnowledgeDocModel(
            id=str(uuid4()),
            title="Email Server Down Runbook",
            content=(
                "If email server is down: check EMAIL-GATEWAY and Storage-D health, "
                "restart transport services, validate NETWORK-CORE routes, notify Infrastructure team."
            ),
            source="runbook",
            tags=["email", "incident"],
        ),
        KnowledgeDocModel(
            id=str(uuid4()),
            title="Network Issue SOP",
            content=(
                "For network issues: verify VPN/firewall rules, test DNS, engage Infrastructure. "
                "Primary assignee profile: John on Infrastructure team."
            ),
            source="sop",
            tags=["network", "sop"],
        ),
        KnowledgeDocModel(
            id=str(uuid4()),
            title="Storage Failure Impact PDF Notes",
            content=(
                "Storage-D failure impacts Database-C and Application-B. "
                "Also review EMAIL-GATEWAY dependency on Storage-D before declaring recovery."
            ),
            source="pdf",
            tags=["storage", "graphrag"],
        ),
    ]
    db.add_all(docs)
    await db.commit()

    for doc in docs:
        vector_store.index_document(doc.title, doc.content, source=doc.source, doc_id=doc.id)


async def ensure_demo_tickets(db: AsyncSession) -> None:
    """Seed sample tickets across all statuses and priorities when the table is empty."""
    from app.domain.value_objects.ticket_state import TicketState
    from app.infrastructure.db.models import TicketModel

    existing = (await db.scalars(select(TicketModel).limit(1))).first()
    if existing:
        return

    now = datetime.now(timezone.utc)
    samples = [
        ("INC1001", "VPN disconnects for remote users", "Network", TicketState.NEW.value, "P1", "ava.network@example.com", "Network Ops"),
        ("INC1002", "Oracle deadlock on SAP batch", "Database", TicketState.ASSIGNED.value, "P1", "ben.db@example.com", "DBA Team"),
        ("INC1003", "API Gateway 5xx spike", "Application", TicketState.WORK_IN_PROGRESS.value, "P2", "chloe.apps@example.com", "App Support"),
        ("INC1004", "Outlook not opening after update", "Software", TicketState.WAITING_FOR_CUSTOMER.value, "P2", "sam.desktop@example.com", "Desktop Team"),
        ("INC1005", "Password reset for contractor", "Access", TicketState.RESOLVED.value, "P3", "elena.sec@example.com", "SecOps"),
        ("INC1006", "Kubernetes node NotReady", "Infrastructure", TicketState.COMPLETED.value, "P1", "diego.infra@example.com", "Platform"),
        ("INC1007", "Phishing report triage", "Security", TicketState.CLOSED.value, "P2", "elena.sec@example.com", "SecOps"),
        ("INC1008", "Printer offline in HQ floor 3", "Hardware", TicketState.ASSIGNED.value, "P3", "sam.desktop@example.com", "Desktop Team"),
        ("INC1009", "DNS resolution intermittent", "Network", TicketState.WORK_IN_PROGRESS.value, "P1", "john@example.com", "Infrastructure"),
        ("INC1010", "Slow Salesforce page loads", "Application", TicketState.NEW.value, "P3", "chloe.apps@example.com", "App Support"),
    ]
    rows = []
    for number, title, category, state, priority, assignee, group in samples:
        closed = state in {
            TicketState.RESOLVED.value,
            TicketState.COMPLETED.value,
            TicketState.CLOSED.value,
        }
        rows.append(
            TicketModel(
                id=str(uuid4()),
                number=number,
                short_description=title,
                description=f"Demo ticket: {title}",
                category=category,
                subcategory="",
                state=state,
                priority=priority,
                assignment_group=group,
                assigned_to=assignee,
                caller="admin@example.com",
                ai_confidence=0.82,
                ai_summary=f"Demo summary for {title}",
                root_cause_suggestion="",
                sla_due_at=now + timedelta(hours={"P1": 2, "P2": 4, "P3": 6}[priority]),
                sla_breached=False,
                work_notes=[],
                comments=[],
                attachments=[],
                audit_logs=[],
                embeddings=[],
                knowledge_links=[],
                related_incidents=[],
                ticket_metadata={"demo": True},
                created_at=now,
                updated_at=now,
                resolved_at=now if closed else None,
                closed_at=now if state in {TicketState.COMPLETED.value, TicketState.CLOSED.value} else None,
            )
        )
    db.add_all(rows)
    await db.commit()


async def ensure_demo_engineers(db: AsyncSession) -> None:
    """Ensure demo engineers / KB exist even on previously seeded databases."""
    john = (await db.scalars(select(EngineerModel).where(EngineerModel.email == "john@example.com"))).first()
    if not john:
        db.add(
            EngineerModel(
                id=str(uuid4()),
                name="John",
                email="john@example.com",
                skills=["Network", "Infrastructure", "VPN", "Firewall", "DNS"],
                assignment_group="Infrastructure",
                max_workload=8,
                current_workload=1,
            )
        )

    desktop = (
        await db.scalars(select(EngineerModel).where(EngineerModel.email == "sam.desktop@example.com"))
    ).first()
    if not desktop:
        db.add(
            EngineerModel(
                id=str(uuid4()),
                name="Sam Desktop",
                email="sam.desktop@example.com",
                skills=["Outlook", "Desktop", "Endpoint", "Software", "Windows"],
                assignment_group="Desktop Team",
                max_workload=8,
                current_workload=1,
            )
        )

    kb = (
        await db.scalars(select(KnowledgeDocModel).where(KnowledgeDocModel.title == "KB-2025-889 Outlook Cache Reset"))
    ).first()
    if not kb:
        kb = KnowledgeDocModel(
            id="KB-2025-889",
            title="KB-2025-889 Outlook Cache Reset",
            content=(
                "Restart Outlook Cache: close Outlook, clear OST cache / run /resetnavpane, "
                "repair Office click-to-run, reopen Outlook. Common after Windows or Office updates "
                "when Outlook will not open."
            ),
            source="kb",
            tags=["outlook", "software", "desktop", "KB-2025-889"],
        )
        db.add(kb)
        await db.flush()
        vector_store.index_document(
            kb.title,
            kb.content,
            source=kb.source,
            doc_id=kb.id,
            extra={"kb_id": "KB-2025-889"},
        )
    else:
        vector_store.index_document(
            kb.title,
            kb.content,
            source=kb.source,
            doc_id=kb.id,
            extra={"kb_id": "KB-2025-889"},
        )

    await db.commit()
