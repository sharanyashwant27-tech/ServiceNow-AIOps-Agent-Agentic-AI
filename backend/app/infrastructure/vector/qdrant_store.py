from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from app.core.config import get_settings
from app.infrastructure.llm.embeddings import cosine_similarity, embed_text

logger = logging.getLogger(__name__)


@dataclass
class VectorHit:
    id: str
    score: float
    payload: dict[str, Any]


@dataclass
class InMemoryVectorStore:
    points: dict[str, dict[str, Any]] = field(default_factory=dict)

    def upsert(self, point_id: str, vector: list[float], payload: dict[str, Any]) -> None:
        self.points[point_id] = {"vector": vector, "payload": payload}

    def search(self, vector: list[float], limit: int = 5) -> list[VectorHit]:
        scored: list[VectorHit] = []
        for pid, point in self.points.items():
            score = cosine_similarity(vector, point["vector"])
            scored.append(VectorHit(id=pid, score=score, payload=point["payload"]))
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:limit]


class VectorKnowledgeStore:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._memory = InMemoryVectorStore()
        self._client = None
        self._init_client()

    def _init_client(self) -> None:
        # Local/demo mode skips remote Qdrant probes for fast startup.
        if self.settings.use_inmemory_fallback:
            return
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http.models import Distance, VectorParams

            self._client = QdrantClient(url=self.settings.qdrant_url, timeout=2.0)
            names = [c.name for c in self._client.get_collections().collections]
            if self.settings.qdrant_collection not in names:
                self._client.create_collection(
                    collection_name=self.settings.qdrant_collection,
                    vectors_config=VectorParams(
                        size=self.settings.embedding_dim, distance=Distance.COSINE
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Qdrant unavailable, using in-memory vectors: %s", exc)
            self._client = None

    def index_document(
        self,
        title: str,
        content: str,
        source: str = "kb",
        doc_id: str | None = None,
        extra: dict | None = None,
    ) -> str:
        point_id = doc_id or str(uuid4())
        vector = embed_text(f"{title}\n{content}")
        payload = {"title": title, "content": content, "source": source, **(extra or {})}
        if self._client is not None:
            try:
                from qdrant_client.http.models import PointStruct

                self._client.upsert(
                    collection_name=self.settings.qdrant_collection,
                    points=[PointStruct(id=point_id, vector=vector, payload=payload)],
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Qdrant upsert failed, memory fallback: %s", exc)
                self._memory.upsert(point_id, vector, payload)
        else:
            self._memory.upsert(point_id, vector, payload)
        return point_id

    def search(self, query: str, limit: int = 5) -> list[VectorHit]:
        vector = embed_text(query)
        if self._client is not None:
            try:
                results = self._client.search(
                    collection_name=self.settings.qdrant_collection,
                    query_vector=vector,
                    limit=limit,
                )
                return [
                    VectorHit(id=str(r.id), score=float(r.score), payload=r.payload or {})
                    for r in results
                ]
            except Exception as exc:  # noqa: BLE001
                logger.warning("Qdrant search failed, memory fallback: %s", exc)
        return self._memory.search(vector, limit=limit)

    def source_counts(self) -> dict[str, int]:
        """Count indexed documents by source (KB usage chart)."""
        counts: dict[str, int] = {}
        for point in self._memory.points.values():
            source = (point.get("payload") or {}).get("source") or "unknown"
            counts[source] = counts.get(source, 0) + 1
        return counts


vector_store = VectorKnowledgeStore()
