from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dto.schemas import DashboardOut, EngineerOut
from app.application.use_cases.ticket_service import TicketService
from app.infrastructure.db.models import EngineerModel, UserModel
from app.infrastructure.db.session import get_db
from app.infrastructure.graph.neo4j_store import graph_store
from app.infrastructure.vector.qdrant_store import vector_store
from app.interfaces.api.deps import get_current_user

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardOut)
async def dashboard(
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(get_current_user),
) -> dict:
    return await TicketService(db).dashboard()


@router.get("/engineers", response_model=list[EngineerOut])
async def engineers(
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(get_current_user),
) -> list[EngineerModel]:
    return list((await db.scalars(select(EngineerModel))).all())


@router.get("/knowledge/search")
async def knowledge_search(q: str, _: UserModel = Depends(get_current_user)) -> dict:
    hits = vector_store.search(q, limit=8)
    return {
        "query": q,
        "results": [
            {"id": h.id, "score": h.score, "title": h.payload.get("title"), "snippet": (h.payload.get("content") or "")[:300]}
            for h in hits
        ],
    }


@router.get("/graph/ci/{ci_name}")
async def graph_ci(ci_name: str, _: UserModel = Depends(get_current_user)) -> dict:
    from app.infrastructure.graph.pipeline import graphrag_pipeline

    # Prefer full GraphRAG Pipeline while keeping CI analyze response shape
    return graphrag_pipeline.run(
        ticket={"title": f"{ci_name} analysis", "description": f"{ci_name} failure", "configuration_item": ci_name},
        ci=ci_name,
        description=f"{ci_name} failure",
    )


@router.get("/incidents/search")
async def search_incidents(
    q: str,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(get_current_user),
) -> dict:
    """Semantic search across previous incidents + learned resolutions."""
    if not q.strip():
        raise HTTPException(status_code=400, detail="query required")
    results = await TicketService(db).search_previous_incidents(q, limit=limit)
    return {"query": q, "count": len(results), "results": results}
