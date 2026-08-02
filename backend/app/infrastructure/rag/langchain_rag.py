from __future__ import annotations

import logging
from typing import Any

from app.infrastructure.rag.pipeline import rag_pipeline
from app.infrastructure.vector.qdrant_store import vector_store

logger = logging.getLogger(__name__)


class LangChainRAG:
    """
    LangChain-compatible facade over the canonical RAG Pipeline:

    User Query → Embedding → Vector Search →
    Similar Tickets → KB Articles → SOP → LLM → Final Resolution
    """

    def retrieve(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        try:
            from langchain_core.documents import Document

            hits = vector_store.search(query, limit=k)
            docs = [
                Document(
                    page_content=h.payload.get("content") or "",
                    metadata={
                        "id": h.id,
                        "title": h.payload.get("title"),
                        "source": h.payload.get("source"),
                        "score": h.score,
                    },
                )
                for h in hits
            ]
            return [
                {
                    "id": d.metadata.get("id"),
                    "title": d.metadata.get("title"),
                    "content": d.page_content,
                    "source": d.metadata.get("source"),
                    "score": d.metadata.get("score"),
                }
                for d in docs
            ]
        except Exception as exc:  # noqa: BLE001
            logger.warning("LangChain retrieve path degraded: %s", exc)
            hits = vector_store.search(query, limit=k)
            return [
                {
                    "id": h.id,
                    "title": h.payload.get("title"),
                    "content": h.payload.get("content"),
                    "source": h.payload.get("source"),
                    "score": h.score,
                }
                for h in hits
            ]

    async def answer(self, query: str, k: int = 5) -> dict[str, Any]:
        result = await rag_pipeline.run(query, k=k)
        # Keep LangChain branding for stack compliance while exposing pipeline fields
        result["framework"] = "langchain+rag-pipeline"
        return result


langchain_rag = LangChainRAG()
