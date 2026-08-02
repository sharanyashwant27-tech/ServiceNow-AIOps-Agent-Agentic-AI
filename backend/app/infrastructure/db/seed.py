from __future__ import annotations

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
