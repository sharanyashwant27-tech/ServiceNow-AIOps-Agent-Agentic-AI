"""Canonical GraphRAG Pipeline for CI impact and RCA."""

from __future__ import annotations

GRAPHRAG_PIPELINE = {
    "name": "GraphRAG Pipeline",
    "steps": [
        {"id": "ticket", "title": "Ticket", "type": "input"},
        {"id": "neo4j", "title": "Neo4j", "type": "store"},
        {"id": "find_related_ci", "title": "Find Related CI", "type": "query"},
        {"id": "find_dependencies", "title": "Find Dependencies", "type": "query"},
        {"id": "find_previous_failures", "title": "Find Previous Failures", "type": "query"},
        {"id": "generate_rca", "title": "Generate RCA", "type": "generate"},
        {"id": "return_impact_analysis", "title": "Return Impact Analysis", "type": "output"},
    ],
}
