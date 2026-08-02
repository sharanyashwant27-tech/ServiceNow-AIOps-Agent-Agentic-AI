"""
RAG Pipeline execution:

User Query → Embedding → Vector Search →
Retrieve Similar Tickets → Retrieve KB Articles → Retrieve SOP →
LLM → Final Resolution
"""

from __future__ import annotations

from typing import Any

from app.domain.rag_pipeline import KB_SOURCES, RAG_PIPELINE, SOP_SOURCES, TICKET_SOURCES
from app.infrastructure.llm.embeddings import embed_text
from app.infrastructure.vector.qdrant_store import vector_store


class RAGPipeline:
    def definition(self) -> dict[str, Any]:
        return RAG_PIPELINE

    async def run(self, query: str, k: int = 8) -> dict[str, Any]:
        from app.infrastructure.llm.provider import llm_provider

        trace: list[dict[str, Any]] = []

        # 1. User Query
        user_query = (query or "").strip()
        trace.append({"id": "user_query", "title": "User Query", "status": "completed", "detail": user_query})

        # 2. Embedding
        embedding = embed_text(user_query)
        trace.append(
            {
                "id": "embedding",
                "title": "Embedding",
                "status": "completed",
                "detail": f"dim={len(embedding)}",
            }
        )

        # 3. Vector Search
        hits = vector_store.search(user_query, limit=max(k, 12))
        trace.append(
            {
                "id": "vector_search",
                "title": "Vector Search",
                "status": "completed",
                "detail": f"{len(hits)} hits",
            }
        )

        def _as_doc(h) -> dict[str, Any]:
            return {
                "id": h.id,
                "title": h.payload.get("title"),
                "content": h.payload.get("content"),
                "source": h.payload.get("source"),
                "kb_id": h.payload.get("kb_id"),
                "score": round(float(h.score), 4),
            }

        # 4–6. Retrieve by corpus type
        similar_tickets = [_as_doc(h) for h in hits if (h.payload.get("source") or "") in TICKET_SOURCES][:5]
        kb_articles = [_as_doc(h) for h in hits if (h.payload.get("source") or "") in KB_SOURCES][:5]
        sop_docs = [_as_doc(h) for h in hits if (h.payload.get("source") or "") in SOP_SOURCES][:5]

        # If buckets are thin, backfill from remaining hits (still labeled by source)
        if len(similar_tickets) < 2:
            for h in hits:
                doc = _as_doc(h)
                if doc not in similar_tickets and doc["source"] in TICKET_SOURCES | {"incident"}:
                    similar_tickets.append(doc)
                if len(similar_tickets) >= 3:
                    break
        if len(kb_articles) < 2:
            for h in hits:
                doc = _as_doc(h)
                if doc["id"] not in {d["id"] for d in kb_articles} and (doc["source"] in KB_SOURCES or doc.get("kb_id")):
                    kb_articles.append(doc)
                if len(kb_articles) >= 3:
                    break
        if len(sop_docs) < 1:
            for h in hits:
                doc = _as_doc(h)
                src = (doc["source"] or "").lower()
                title = (doc["title"] or "").lower()
                if doc["id"] not in {d["id"] for d in sop_docs} and ("sop" in src or "sop" in title or "runbook" in src):
                    sop_docs.append(doc)
                if len(sop_docs) >= 2:
                    break

        trace.append(
            {
                "id": "retrieve_similar_tickets",
                "title": "Retrieve Similar Tickets",
                "status": "completed",
                "detail": f"{len(similar_tickets)} tickets",
                "items": similar_tickets,
            }
        )
        trace.append(
            {
                "id": "retrieve_kb_articles",
                "title": "Retrieve KB Articles",
                "status": "completed",
                "detail": f"{len(kb_articles)} articles",
                "items": kb_articles,
            }
        )
        trace.append(
            {
                "id": "retrieve_sop",
                "title": "Retrieve SOP",
                "status": "completed",
                "detail": f"{len(sop_docs)} SOP/runbooks",
                "items": sop_docs,
            }
        )

        # 7. LLM
        context_blocks = []
        for label, docs in (
            ("Similar Tickets", similar_tickets),
            ("KB Articles", kb_articles),
            ("SOP", sop_docs),
        ):
            if not docs:
                continue
            context_blocks.append(f"### {label}")
            for i, d in enumerate(docs, 1):
                context_blocks.append(
                    f"[{label[:1]}{i}] {d.get('title')} (score={d.get('score')})\n{(d.get('content') or '')[:500]}"
                )
        context = "\n\n".join(context_blocks) or "No documents retrieved."

        prompt = (
            "You are a ServiceNow AIOps RAG assistant.\n"
            "Using Similar Tickets, KB Articles, and SOP context, produce a Final Resolution.\n"
            "Be concise and actionable. Prefer steps an engineer can execute.\n\n"
            f"User Query: {user_query}\n\n"
            f"Retrieved Context:\n{context}\n\n"
            "Final Resolution:"
        )
        completion = await llm_provider.complete(
            prompt,
            system="Follow the RAG Pipeline. Output a clear Final Resolution with numbered steps when possible.",
        )
        llm_text = (completion.get("text") or "").strip()
        trace.append(
            {
                "id": "llm",
                "title": "LLM",
                "status": "completed",
                "detail": f"{completion.get('provider')}/{completion.get('model')}",
            }
        )

        # 8. Final Resolution (LLM + deterministic fallback from top docs)
        final_resolution = llm_text or self._fallback_resolution(user_query, similar_tickets, kb_articles, sop_docs)
        trace.append(
            {
                "id": "final_resolution",
                "title": "Final Resolution",
                "status": "completed",
                "detail": final_resolution[:240],
            }
        )

        documents = similar_tickets + kb_articles + sop_docs
        return {
            "pipeline": RAG_PIPELINE,
            "query": user_query,
            "embedding_dim": len(embedding),
            "similar_tickets": similar_tickets,
            "kb_articles": kb_articles,
            "sop": sop_docs,
            "documents": documents,
            "llm": {
                "provider": completion.get("provider"),
                "model": completion.get("model"),
                "raw": llm_text,
            },
            "final_resolution": final_resolution,
            "answer": final_resolution,  # alias for existing clients
            "trace": trace,
            "framework": "rag-pipeline",
        }

    def _fallback_resolution(
        self,
        query: str,
        tickets: list[dict[str, Any]],
        kb: list[dict[str, Any]],
        sop: list[dict[str, Any]],
    ) -> str:
        top = (kb or sop or tickets or [{}])[0]
        title = top.get("title") or "standard remediation"
        snippet = (top.get("content") or "").strip()
        steps = [s.strip() for s in snippet.split(".") if s.strip()][:4]
        if not steps:
            steps = [
                "Confirm the reported symptom and affected CI",
                f"Apply guidance from {title}",
                "Validate service recovery with the user",
            ]
        numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
        return f"Final Resolution for: {query}\n\nBased on: {title}\n\n{numbered}"


rag_pipeline = RAGPipeline()
