import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import ClickableCard from "../components/ClickableCard";
import { ARCH_NODE_HREFS, archAgentHref } from "../nav/cardLinks";
import { api } from "../services/api";

function ArchNode({ label, className = "" }: { label: string; className?: string }) {
  return (
    <ClickableCard
      to={ARCH_NODE_HREFS[label] || "/"}
      className={`arch-node ${className}`.trim()}
      title={`Open ${label}`}
    >
      {label}
    </ClickableCard>
  );
}

export default function ArchitecturePage() {
  const [arch, setArch] = useState<any>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.architecture()
      .then(setArch)
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!arch) return <p>Loading architecture…</p>;

  const subAgents = arch.layers.find((l: any) => l.id === "sub_agents")?.agents || [];
  const channels = arch.layers.find((l: any) => l.id === "channels")?.channels || [];

  return (
    <div className="page">
      <header className="page-header">
        <h1>System architecture</h1>
        <p>{arch.name} — click any node or agent card to open its page.</p>
      </header>

      <div className="arch">
        <ArchNode label="Users" className="arch-users" />
        <div className="arch-line" />
        <ArchNode label="React Service Portal" />
        <div className="arch-line" />
        <ArchNode label="FastAPI Backend" />
        <div className="arch-line" />
        <ArchNode label="Master AI Agent" className="arch-master" />
        <div className="arch-line" />

        <div className="arch-agents arch-agents-8">
          {subAgents.map((a: any) => (
            <ClickableCard
              key={a.id}
              to={archAgentHref(String(a.id || a.name || ""))}
              className="arch-agent"
              title={`Open ${a.name}`}
            >
              <strong>{a.name?.replace(/^Sub Agent \d+ — /, "") || a.name}</strong>
              <ul>
                {a.detects?.slice(0, 2).map((r: string) => (
                  <li key={r}>{r}</li>
                ))}
                {a.uses && Array.isArray(a.uses)
                  ? a.uses.slice(0, 2).map((r: string) => <li key={r}>{r}</li>)
                  : null}
                {a.channels?.slice(0, 2).map((r: string) => (
                  <li key={r}>{r}</li>
                ))}
                {a.example?.output && typeof a.example.output === "string" && <li>→ {a.example.output}</li>}
                {a.example?.output?.assign && (
                  <li>
                    → {a.example.output.assign} / {a.example.output.team}
                  </li>
                )}
                {a.escalates && <li>{a.escalates}</li>}
                {a.threshold && <li>Threshold {a.threshold}</li>}
              </ul>
            </ClickableCard>
          ))}
        </div>

        <div className="arch-line" />
        <ArchNode label="RAG Engine" />
        <div className="arch-line" />
        <ArchNode label="Vector DB + Neo4j GraphRAG" />
        <div className="arch-line" />
        <ArchNode label="ServiceNow Database" />
        <div className="arch-line" />
        <ArchNode label="n8n Workflow" />
        <div className="arch-line" />
        <div className="arch-channels">
          {channels.map((c: string) => (
            <Link key={c} to="/automation" className="arch-channel-chip">
              {c}
            </Link>
          ))}
        </div>
      </div>

      {(arch.ticket_workflow || []).length > 0 && (
        <section className="panel" style={{ marginTop: "1rem" }}>
          <ClickableCard to="/workflow" className="panel-link-header" title="Open Workflow">
            <h2>Ticket workflow</h2>
            <span className="panel-link-cta">View →</span>
          </ClickableCard>
          <ol className="flow-list">
            {arch.ticket_workflow.map((step: string) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        </section>
      )}

      {(arch.ticket_status || []).length > 0 && (
        <section className="panel" style={{ marginTop: "1rem" }}>
          <ClickableCard to="/workflow" className="panel-link-header" title="Open Status">
            <h2>Ticket status</h2>
            <span className="panel-link-cta">View →</span>
          </ClickableCard>
          <ol className="flow-list">
            {arch.ticket_status.map((step: string) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        </section>
      )}

      <section className="panel" style={{ marginTop: "1rem" }}>
        <ClickableCard to="/automation" className="panel-link-header" title="Open Automation">
          <h2>Sub-agent catalog</h2>
          <span className="panel-link-cta">View →</span>
        </ClickableCard>
        <ul className="list">
          {subAgents.map((a: any) => (
            <li key={a.id}>
              <ClickableCard to={archAgentHref(String(a.id || ""))} className="list-card-link">
                <div>
                  <strong>{a.name}</strong>
                  <span>{JSON.stringify(a.example || a.levels || a.returns || a.timers || a.channels || a.action)}</span>
                </div>
              </ClickableCard>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
