from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class GraphEdge:
    source: str
    target: str
    relation: str


@dataclass
class InMemoryGraph:
    nodes: set[str] = field(default_factory=set)
    edges: list[GraphEdge] = field(default_factory=list)

    def upsert_dependency(self, source: str, target: str, relation: str = "DEPENDS_ON") -> None:
        self.nodes.add(source)
        self.nodes.add(target)
        self.edges.append(GraphEdge(source=source, target=target, relation=relation))

    def dependents(self, ci: str) -> list[str]:
        return [e.target for e in self.edges if e.source == ci]

    def dependencies(self, ci: str) -> list[str]:
        # nodes that this CI depends on
        return [e.target for e in self.edges if e.source == ci]

    def depended_by(self, ci: str) -> list[str]:
        # nodes that depend on this CI
        return [e.source for e in self.edges if e.target == ci]

    def blast_radius(self, ci: str, depth: int = 3) -> list[str]:
        """Downstream dependents recursively."""
        seen = {ci}
        frontier = {ci}
        for _ in range(depth):
            nxt: set[str] = set()
            for node in frontier:
                for dep in self.dependents(node):
                    if dep not in seen:
                        seen.add(dep)
                        nxt.add(dep)
            frontier = nxt
        seen.discard(ci)
        return sorted(seen)

    def upstream_impact(self, ci: str, depth: int = 5) -> list[str]:
        """If CI fails, which services are affected (walk depended_by)."""
        seen = {ci}
        frontier = {ci}
        for _ in range(depth):
            nxt: set[str] = set()
            for node in frontier:
                for parent in self.depended_by(node):
                    if parent not in seen:
                        seen.add(parent)
                        nxt.add(parent)
            frontier = nxt
        seen.discard(ci)
        return sorted(seen)

    def impact_chain(self, ci: str) -> list[str]:
        """Return a readable chain including the failed CI."""
        affected = self.upstream_impact(ci)
        return [ci, *affected]


class GraphStore:
    def __init__(self) -> None:
        from app.core.config import get_settings

        self.settings = get_settings()
        self._memory = InMemoryGraph()
        self._driver = None
        self._seed()
        self._init_driver()

    def _seed(self) -> None:
        # Architecture demo chain:
        # Server-A → Application-B → Database-C → Storage-D → Network-Switch-E
        # Encoded as DEPENDS_ON toward infrastructure dependencies.
        demo_chain = [
            ("Application-B", "Server-A", "RUNS_ON"),
            ("Application-B", "Database-C", "DEPENDS_ON"),
            ("Database-C", "Storage-D", "DEPENDS_ON"),
            ("Storage-D", "Network-Switch-E", "CONNECTED_TO"),
            ("Server-A", "Network-Switch-E", "CONNECTED_TO"),
        ]
        legacy = [
            ("SAP-ERP", "DB-ORACLE-01", "DEPENDS_ON"),
            ("SAP-ERP", "APP-SERVER-12", "RUNS_ON"),
            ("APP-SERVER-12", "NETWORK-CORE", "CONNECTED_TO"),
            ("EMAIL-GATEWAY", "NETWORK-CORE", "CONNECTED_TO"),
            ("EMAIL-GATEWAY", "Storage-D", "DEPENDS_ON"),
            ("VPN-CONCENTRATOR", "NETWORK-CORE", "CONNECTED_TO"),
            ("CRM-CLOUD", "API-GATEWAY", "DEPENDS_ON"),
            ("API-GATEWAY", "K8S-CLUSTER", "RUNS_ON"),
            ("PAYMENT-SVC", "DB-POSTGRES-02", "DEPENDS_ON"),
            ("PAYMENT-SVC", "API-GATEWAY", "DEPENDS_ON"),
        ]
        for s, t, r in demo_chain + legacy:
            self._memory.upsert_dependency(s, t, r)

    def _init_driver(self) -> None:
        if self.settings.use_inmemory_fallback:
            logger.info("Using in-memory GraphRAG store (Neo4j probe skipped)")
            return
        try:
            from neo4j import GraphDatabase

            self._driver = GraphDatabase.driver(
                self.settings.neo4j_uri,
                auth=(self.settings.neo4j_user, self.settings.neo4j_password),
            )
            with self._driver.session() as session:
                session.run("RETURN 1")
            self._sync_seed_to_neo4j()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Neo4j unavailable, using in-memory graph: %s", exc)
            self._driver = None

    def _sync_seed_to_neo4j(self) -> None:
        if not self._driver:
            return
        with self._driver.session() as session:
            for edge in self._memory.edges:
                session.run(
                    """
                    MERGE (a:CI {name:$source})
                    MERGE (b:CI {name:$target})
                    MERGE (a)-[r:REL {type:$rel}]->(b)
                    """,
                    source=edge.source,
                    target=edge.target,
                    rel=edge.relation,
                )

    def analyze_ci(self, ci: str) -> dict:
        in_graph = ci in self._memory.nodes
        deps = self._memory.dependencies(ci) if in_graph else []
        depended_by = self._memory.depended_by(ci) if in_graph else []
        affected = self._memory.upstream_impact(ci) if in_graph else []
        chain = self._memory.impact_chain(ci) if in_graph else [ci]
        suggestion = (
            f"If '{ci}' fails, AI predicts affected services: "
            f"{', '.join(affected) or 'none directly mapped'}. "
            f"Impact chain: {' → '.join(chain)}. "
            f"Direct dependents: {', '.join(depended_by) or 'none'}."
        )
        return {
            "configuration_item": ci,
            "dependencies": deps,
            "dependents": depended_by,
            "affected_services": affected,
            "impact_chain": chain,
            "blast_radius": affected,
            "root_cause_suggestion": suggestion,
            "topology_example": [
                "Server-A",
                "Application-B",
                "Database-C",
                "Storage-D",
                "Network-Switch-E",
            ],
            "backend": "neo4j" if self._driver else "memory",
        }


graph_store = GraphStore()
