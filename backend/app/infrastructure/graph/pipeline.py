"""
GraphRAG Pipeline:

Ticket → Neo4j → Find Related CI → Find Dependencies →
Find Previous Failures → Generate RCA → Return Impact Analysis
"""

from __future__ import annotations

import re
from typing import Any

from app.domain.graphrag_pipeline import GRAPHRAG_PIPELINE
from app.infrastructure.graph.neo4j_store import graph_store
from app.infrastructure.vector.qdrant_store import vector_store


class GraphRAGPipeline:
    def definition(self) -> dict[str, Any]:
        return GRAPHRAG_PIPELINE

    def resolve_ci(self, ticket: dict[str, Any] | None = None, ci: str | None = None, description: str = "") -> str:
        if ci:
            return ci
        ticket = ticket or {}
        candidate = ticket.get("configuration_item") or ticket.get("ci")
        text = f"{candidate or ''} {ticket.get('title') or ticket.get('short_description') or ''} {ticket.get('description') or description}"
        if candidate:
            return str(candidate)
        match = re.search(r"\b([A-Z]{2,}[-_][A-Z0-9-]{2,})\b", text)
        lower = text.lower()
        if "storage" in lower:
            return "Storage-D"
        if "database" in lower or "db " in lower:
            return "Database-C"
        if "switch" in lower:
            return "Network-Switch-E"
        if "application" in lower:
            return "Application-B"
        if "server" in lower:
            return "Server-A"
        if "email" in lower or "outlook" in lower:
            return "EMAIL-GATEWAY"
        if "vpn" in lower:
            return "VPN-CONCENTRATOR"
        if "api" in lower:
            return "API-GATEWAY"
        return match.group(1) if match else "Storage-D"

    def run(
        self,
        ticket: dict[str, Any] | None = None,
        ci: str | None = None,
        description: str = "",
    ) -> dict[str, Any]:
        ticket = ticket or {}
        trace: list[dict[str, Any]] = []

        # 1. Ticket
        ticket_label = (
            ticket.get("number")
            or ticket.get("id")
            or ticket.get("title")
            or ticket.get("short_description")
            or "adhoc"
        )
        ticket_text = (
            f"{ticket.get('title') or ticket.get('short_description') or ''}\n"
            f"{ticket.get('description') or description}"
        ).strip()
        trace.append(
            {
                "id": "ticket",
                "title": "Ticket",
                "status": "completed",
                "detail": str(ticket_label),
            }
        )

        # 2. Neo4j
        backend = "neo4j" if getattr(graph_store, "_driver", None) else "memory"
        trace.append(
            {
                "id": "neo4j",
                "title": "Neo4j",
                "status": "completed",
                "detail": f"graph backend={backend}",
            }
        )

        # 3. Find Related CI
        related_ci = self.resolve_ci(ticket=ticket, ci=ci, description=description or ticket_text)
        trace.append(
            {
                "id": "find_related_ci",
                "title": "Find Related CI",
                "status": "completed",
                "detail": related_ci,
            }
        )

        # 4. Find Dependencies
        analysis = graph_store.analyze_ci(related_ci)
        dependencies = analysis.get("dependencies") or []
        dependents = analysis.get("dependents") or []
        impact_chain = analysis.get("impact_chain") or [related_ci]
        affected = analysis.get("affected_services") or analysis.get("blast_radius") or []
        trace.append(
            {
                "id": "find_dependencies",
                "title": "Find Dependencies",
                "status": "completed",
                "detail": f"{len(dependencies)} deps, {len(dependents)} dependents",
                "dependencies": dependencies,
                "dependents": dependents,
                "impact_chain": impact_chain,
            }
        )

        # 5. Find Previous Failures (vector / historical incidents mentioning CI)
        search_q = f"{related_ci} {ticket_text}".strip()
        hits = vector_store.search(search_q, limit=8)
        previous_failures = []
        for h in hits:
            source = (h.payload.get("source") or "").lower()
            title = h.payload.get("title") or ""
            content = h.payload.get("content") or ""
            if source in {"incident", "learned_incident", "runbook", "kb"} or related_ci.lower() in (
                title + content
            ).lower():
                previous_failures.append(
                    {
                        "id": h.id,
                        "title": title,
                        "source": source,
                        "score": round(float(h.score), 4),
                        "snippet": content[:220],
                    }
                )
            if len(previous_failures) >= 5:
                break
        trace.append(
            {
                "id": "find_previous_failures",
                "title": "Find Previous Failures",
                "status": "completed",
                "detail": f"{len(previous_failures)} historical matches",
                "items": previous_failures,
            }
        )

        # 6. Generate RCA
        hist_line = (
            "; ".join(f["title"] for f in previous_failures[:3])
            if previous_failures
            else "no strongly matching prior incidents"
        )
        rca = (
            f"Root Cause Analysis for {related_ci}: "
            f"Primary CI '{related_ci}' is implicated by the ticket. "
            f"Dependency path: {' → '.join(impact_chain)}. "
            f"Services likely impacted: {', '.join(affected) or 'none mapped'}. "
            f"Historical context: {hist_line}. "
            f"Recommended focus: validate {related_ci} health, then walk upstream dependents "
            f"({', '.join(dependents[:4]) or 'n/a'})."
        )
        trace.append(
            {
                "id": "generate_rca",
                "title": "Generate RCA",
                "status": "completed",
                "detail": rca[:240],
            }
        )

        # 7. Return Impact Analysis
        impact_analysis = {
            "configuration_item": related_ci,
            "dependencies": dependencies,
            "dependents": dependents,
            "affected_services": affected,
            "impact_chain": impact_chain,
            "blast_radius": affected,
            "previous_failures": previous_failures,
            "root_cause_analysis": rca,
            "root_cause_suggestion": rca,
            "severity": "high" if len(affected) >= 2 else ("medium" if affected else "low"),
            "backend": analysis.get("backend", backend),
            "topology_example": analysis.get("topology_example"),
        }
        trace.append(
            {
                "id": "return_impact_analysis",
                "title": "Return Impact Analysis",
                "status": "completed",
                "detail": f"severity={impact_analysis['severity']}, affected={len(affected)}",
            }
        )

        return {
            "pipeline": GRAPHRAG_PIPELINE,
            "ticket": {
                "id": ticket.get("id"),
                "number": ticket.get("number"),
                "title": ticket.get("title") or ticket.get("short_description"),
            },
            "related_ci": related_ci,
            "dependencies": dependencies,
            "dependents": dependents,
            "previous_failures": previous_failures,
            "rca": rca,
            "impact_analysis": impact_analysis,
            # Compatibility with existing GraphRAG / UI consumers
            **{k: v for k, v in impact_analysis.items() if k != "previous_failures"},
            "trace": trace,
            "framework": "graphrag-pipeline",
        }


graphrag_pipeline = GraphRAGPipeline()
