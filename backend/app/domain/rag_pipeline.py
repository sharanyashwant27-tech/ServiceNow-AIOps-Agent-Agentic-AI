"""Canonical RAG Pipeline for resolution generation."""

from __future__ import annotations

RAG_PIPELINE = {
    "name": "RAG Pipeline",
    "steps": [
        {"id": "user_query", "title": "User Query", "type": "input"},
        {"id": "embedding", "title": "Embedding", "type": "process"},
        {"id": "vector_search", "title": "Vector Search", "type": "process"},
        {"id": "retrieve_similar_tickets", "title": "Retrieve Similar Tickets", "type": "retrieve"},
        {"id": "retrieve_kb_articles", "title": "Retrieve KB Articles", "type": "retrieve"},
        {"id": "retrieve_sop", "title": "Retrieve SOP", "type": "retrieve"},
        {"id": "llm", "title": "LLM", "type": "generate"},
        {"id": "final_resolution", "title": "Final Resolution", "type": "output"},
    ],
}

# Vector store source tags used for retrieval buckets
TICKET_SOURCES = {"incident", "learned_incident"}
KB_SOURCES = {"kb", "pdf", "runbook"}
SOP_SOURCES = {"sop", "runbook"}
