from __future__ import annotations

_TICKETS_CREATED = 0
_ESCALATIONS = 0
_RAG_QUERIES = 0


def inc_tickets_created(n: int = 1) -> None:
    global _TICKETS_CREATED
    _TICKETS_CREATED += n


def inc_escalations(n: int = 1) -> None:
    global _ESCALATIONS
    _ESCALATIONS += n


def inc_rag_queries(n: int = 1) -> None:
    global _RAG_QUERIES
    _RAG_QUERIES += n


def snapshot() -> dict[str, int]:
    return {
        "aiops_tickets_created_total": _TICKETS_CREATED,
        "aiops_escalations_total": _ESCALATIONS,
        "aiops_rag_queries_total": _RAG_QUERIES,
    }
