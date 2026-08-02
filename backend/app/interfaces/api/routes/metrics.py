from __future__ import annotations

from fastapi import APIRouter, Response

from app.infrastructure.monitoring.metrics_registry import snapshot

router = APIRouter(tags=["monitoring"])


@router.get("/metrics")
async def prometheus_metrics() -> Response:
    """Prometheus-compatible metrics endpoint."""
    values = snapshot()
    try:
        from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, generate_latest

        registry = CollectorRegistry()
        c_tickets = Counter("aiops_tickets_created_total", "Tickets created", registry=registry)
        c_esc = Counter("aiops_escalations_total", "SLA escalations", registry=registry)
        c_rag = Counter("aiops_rag_queries_total", "RAG queries", registry=registry)
        if values["aiops_tickets_created_total"]:
            c_tickets.inc(values["aiops_tickets_created_total"])
        if values["aiops_escalations_total"]:
            c_esc.inc(values["aiops_escalations_total"])
        if values["aiops_rag_queries_total"]:
            c_rag.inc(values["aiops_rag_queries_total"])
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
    except Exception:
        body = "".join(
            f"# TYPE {k} counter\n{k} {v}\n" for k, v in values.items()
        )
        return Response(body, media_type="text/plain; version=0.0.4; charset=utf-8")
