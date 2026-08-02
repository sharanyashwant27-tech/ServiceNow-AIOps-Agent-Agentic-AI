import { useEffect, useState } from "react";
import ClickableCard from "../components/ClickableCard";
import { statusStepHref, workflowStepHref } from "../nav/cardLinks";
import { api } from "../services/api";

export default function WorkflowPage() {
  const [workflow, setWorkflow] = useState<any>(null);
  const [status, setStatus] = useState<any>(null);
  const [entity, setEntity] = useState<any>(null);
  const [n8n, setN8n] = useState<any>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api.ticketWorkflow(), api.ticketStatus(), api.ticketEntity(), api.n8nWorkflowDefinition()])
      .then(([wf, st, ent, n8]) => {
        setWorkflow(wf);
        setStatus(st);
        setEntity(ent);
        setN8n(n8);
      })
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!workflow || !status || !entity || !n8n) return <p>Loading workflows…</p>;

  return (
    <div className="page">
      <header className="page-header">
        <h1>Ticket Workflow, Status & Entity</h1>
        <p>Click a step card to open Tickets, Automation, or Knowledge.</p>
      </header>

      <div className="grid-2">
        <section className="panel workflow-panel">
          <h2>{workflow.name}</h2>
          <ol className="workflow-flow">
            {workflow.steps.map((step: any, idx: number) => (
              <li key={step.id}>
                <ClickableCard
                  to={workflowStepHref(step)}
                  className={`workflow-step type-${step.type}`}
                  title={`Open ${step.title}`}
                >
                  <span className="workflow-idx">{idx + 1}</span>
                  <div>
                    <strong>{step.title}</strong>
                    <em>{step.type}</em>
                  </div>
                </ClickableCard>
                {idx < workflow.steps.length - 1 && (
                  <span className="workflow-arrow" aria-hidden>
                    ↓
                  </span>
                )}
              </li>
            ))}
          </ol>
        </section>

        <section className="panel workflow-panel">
          <h2>{status.name}</h2>
          <ol className="workflow-flow">
            {status.steps.map((step: any, idx: number) => (
              <li key={step.id}>
                <ClickableCard
                  to={statusStepHref(step.code)}
                  className="workflow-step type-state"
                  title={`Tickets in ${step.code}`}
                >
                  <span className="workflow-idx">{idx + 1}</span>
                  <div>
                    <strong>{step.code}</strong>
                    <em>{step.title}</em>
                  </div>
                </ClickableCard>
                {idx < status.steps.length - 1 && (
                  <span className="workflow-arrow" aria-hidden>
                    ↓
                  </span>
                )}
              </li>
            ))}
          </ol>
        </section>
      </div>

      <section className="panel" style={{ marginTop: "1rem" }}>
        <ClickableCard to="/tickets" className="panel-link-header" title="Open Tickets">
          <h2>{entity.name} entity</h2>
          <span className="panel-link-cta">View →</span>
        </ClickableCard>
        <ul className="entity-fields">
          {entity.fields.map((f: string) => (
            <li key={f}>
              <strong>{f}</strong>
              <span>{entity.mapping?.[f] || ""}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel" style={{ marginTop: "1rem" }}>
        <ClickableCard to="/automation" className="panel-link-header" title="Open Automation">
          <h2>
            {n8n.name} — {n8n.trigger}
          </h2>
          <span className="panel-link-cta">View →</span>
        </ClickableCard>
        <ol className="workflow-flow rag-flow">
          {n8n.steps.map((step: any, idx: number) => (
            <li key={step.id}>
              <ClickableCard
                to="/automation"
                className="workflow-step type-integration"
                title="Open Automation"
              >
                <span className="workflow-idx">{idx + 1}</span>
                <div>
                  <strong>{step.title}</strong>
                  <em>{step.type}</em>
                </div>
              </ClickableCard>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
