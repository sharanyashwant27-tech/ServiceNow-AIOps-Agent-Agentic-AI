import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import ClickableCard from "../components/ClickableCard";
import { api } from "../services/api";

function capabilityHref(c: { id?: string; endpoint?: string; agent?: string }): string {
  const id = (c.id || "").toLowerCase();
  if (id === "dashboards") return "/";
  if (["rag_resolve", "search", "rca", "learn"].includes(id)) return "/knowledge";
  if (["classify", "duplicates", "assign", "prioritize", "auto_create", "resolution"].includes(id)) {
    return "/tickets";
  }
  if (["sla", "escalate", "sla_breach", "notify"].includes(id)) return "/automation";
  return "/automation";
}

export default function AutomationPage() {
  const [caps, setCaps] = useState<any[]>([]);
  const [alertName, setAlertName] = useState("API-GATEWAY-5XX-SPIKE");
  const [severity, setSeverity] = useState("critical");
  const [message, setMessage] = useState("Elevated 5xx on API-GATEWAY impacting CRM-CLOUD users");
  const [ci, setCi] = useState("API-GATEWAY");
  const [query, setQuery] = useState("oracle deadlock SAP");
  const [created, setCreated] = useState<any>(null);
  const [search, setSearch] = useState<any>(null);
  const [escalation, setEscalation] = useState<any>(null);
  const [error, setError] = useState("");
  const [n8nDef, setN8nDef] = useState<any>(null);
  const [n8nRun, setN8nRun] = useState<any>(null);
  const [n8nRunning, setN8nRunning] = useState(false);
  const [slaDef, setSlaDef] = useState<any>(null);
  const [slaRun, setSlaRun] = useState<any>(null);
  const [slaRunning, setSlaRunning] = useState(false);
  const [resolutionDef, setResolutionDef] = useState<any>(null);

  useEffect(() => {
    Promise.all([
      api.capabilities(),
      api.n8nWorkflowDefinition(),
      api.slaBreachWorkflowDefinition(),
      api.resolutionWorkflowDefinition(),
    ])
      .then(([capsRes, n8n, sla, res]) => {
        setCaps(capsRes.capabilities || []);
        setN8nDef(n8n);
        setSlaDef(sla);
        setResolutionDef(res);
      })
      .catch((e) => setError(e.message));
  }, []);

  async function runN8n() {
    setN8nRunning(true);
    setError("");
    try {
      setN8nRun(await api.n8nTicketCreatedRun(message || alertName, message));
    } catch (err: any) {
      setError(err.message);
    } finally {
      setN8nRunning(false);
    }
  }

  async function ingest(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      setCreated(
        await api.ingestAlert({
          alert_name: alertName,
          severity,
          message,
          configuration_item: ci,
          source: "monitoring",
        })
      );
    } catch (err: any) {
      setError(err.message);
    }
  }

  async function runSearch(e: FormEvent) {
    e.preventDefault();
    setSearch(await api.searchIncidents(query));
  }

  async function escalate() {
    setEscalation(await api.escalateOverdue());
  }

  async function runSlaBreach() {
    setSlaRunning(true);
    setError("");
    try {
      setSlaRun(await api.slaBreachWorkflowRun());
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSlaRunning(false);
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <h1>AI automation control center</h1>
        <p>Auto-create, search history, escalate overdue SLAs, and review platform capabilities.</p>
      </header>

      {error && <p className="error">{error}</p>}

      {n8nDef && (
        <section className="panel" style={{ marginBottom: "1rem" }}>
          <h2>
            {n8nDef.name} — {n8nDef.trigger}
          </h2>
          <ol className="workflow-flow rag-flow">
            {n8nDef.steps.map((step: any, idx: number) => (
              <li key={step.id} className="workflow-step type-integration">
                <span className="workflow-idx">{idx + 1}</span>
                <div>
                  <strong>{step.title}</strong>
                  <em>{step.type}</em>
                </div>
              </li>
            ))}
          </ol>
          <div className="note-compose-actions" style={{ marginTop: "0.75rem" }}>
            <button type="button" onClick={runN8n} disabled={n8nRunning}>
              {n8nRunning ? "Running n8n…" : "Run Ticket Created workflow"}
            </button>
          </div>
          {n8nRun && (
            <>
              <ul className="workflow-trace" style={{ marginTop: "0.75rem" }}>
                {(n8nRun.trace || []).map((s: any) => (
                  <li key={s.id}>
                    <span>{s.title}</span>
                    <span className={s.status === "completed" ? "ok" : "pending"}>{s.detail || s.status}</span>
                  </li>
                ))}
              </ul>
              <p className="hint">
                run_id {n8nRun.run_id} · importable JSON at <code>n8n/ticket-created-workflow.json</code>
              </p>
            </>
          )}
        </section>
      )}

      <section className="panel">
        <h2>Platform capabilities</h2>
        <ul className="list">
          {caps.map((c) => (
            <li key={c.id}>
              <ClickableCard to={capabilityHref(c)} className="list-card-link" title={`Open ${c.name}`}>
                <div>
                  <strong>{c.name}</strong>
                  <span>{c.agent || c.endpoint || c.trigger || "enabled"}</span>
                </div>
              </ClickableCard>
            </li>
          ))}
        </ul>
      </section>

      <div className="grid-2">
        <section className="panel">
          <h2>Create ticket from alert</h2>
          <form className="form-grid" onSubmit={ingest}>
            <label>
              Alert name
              <input value={alertName} onChange={(e) => setAlertName(e.target.value)} required />
            </label>
            <label>
              Severity
              <input value={severity} onChange={(e) => setSeverity(e.target.value)} />
            </label>
            <label>
              Configuration item
              <input value={ci} onChange={(e) => setCi(e.target.value)} />
            </label>
            <label className="full">
              Message
              <textarea value={message} onChange={(e) => setMessage(e.target.value)} rows={3} required />
            </label>
            <button>Auto-create & triage</button>
          </form>
          {created && (
            <p className="hint">
              Created{" "}
              <Link to={`/tickets/${created.ticket.id}`}>{created.ticket.number}</Link> · {created.ticket.priority} ·{" "}
              {created.ticket.assigned_to} · confidence {Math.round(created.overall_confidence * 100)}%
            </p>
          )}
        </section>

        <section className="panel">
          <h2>Search previous incidents</h2>
          <form className="inline-form" onSubmit={runSearch}>
            <input value={query} onChange={(e) => setQuery(e.target.value)} />
            <button>Search</button>
          </form>
          <ul className="list">
            {(search?.results || []).map((r: any, idx: number) => (
              <li key={`${r.id}-${idx}`}>
                <ClickableCard
                  to={r.id ? `/tickets/${r.id}` : "/knowledge"}
                  className="list-card-link"
                  title="Open related ticket or knowledge"
                >
                  <div>
                    <strong>
                      {r.number || r.short_description} ({Math.round((r.score || 0) * 100)}%)
                    </strong>
                    <span>{r.ai_summary || r.short_description}</span>
                  </div>
                </ClickableCard>
              </li>
            ))}
          </ul>
        </section>

        <section className="panel">
          <h2>Escalate overdue incidents</h2>
          <p className="hint">Scans open tickets past SLA due time, raises priority, and notifies engineers.</p>
          <button onClick={escalate}>Run escalation sweep</button>
          {escalation && (
            <p className="hint">
              Escalated {escalation.escalated_count} ticket(s)
              {(escalation.tickets || []).map((t: any) => ` · ${t.number} ${t.from_priority}→${t.to_priority}`).join("")}
            </p>
          )}
        </section>

        {slaDef && (
          <section className="panel">
            <h2>
              {slaDef.name} — {slaDef.trigger}
            </h2>
            <ol className="workflow-flow rag-flow">
              {slaDef.steps.map((step: any, idx: number) => (
                <li key={step.id} className="workflow-step type-state">
                  <span className="workflow-idx">{idx + 1}</span>
                  <div>
                    <strong>{step.title}</strong>
                    <em>{step.type}</em>
                  </div>
                </li>
              ))}
            </ol>
            <button type="button" style={{ marginTop: "0.75rem" }} onClick={runSlaBreach} disabled={slaRunning}>
              {slaRunning ? "Running cron…" : "Run SLA Breach cron now"}
            </button>
            {slaRun && (
              <>
                <ul className="workflow-trace" style={{ marginTop: "0.75rem" }}>
                  {(slaRun.trace || []).map((s: any) => (
                    <li key={s.id}>
                      <span>{s.title}</span>
                      <span className="ok">{s.detail || s.status}</span>
                    </li>
                  ))}
                </ul>
                <p className="hint">
                  expired {slaRun.expired_count} · processed {slaRun.processed_count}
                  {(slaRun.tickets || [])
                    .map((t: any) => ` · ${t.number} ${t.from_priority}→${t.to_priority} RCA ${t.rca_task_id?.slice(0, 8)}`)
                    .join("")}
                </p>
              </>
            )}
          </section>
        )}

        <section className="panel">
          <h2>Learning loop</h2>
          <p className="rca">
            When a ticket moves to Resolved, Completed, or Closed, the learning agent indexes the problem statement,
            RCA, and work notes into the vector store so future RAG resolution suggestions improve automatically.
          </p>
        </section>

        {resolutionDef && (
          <section className="panel">
            <h2>
              {resolutionDef.name} — {resolutionDef.trigger}
            </h2>
            <ol className="workflow-flow rag-flow">
              {resolutionDef.steps.map((step: any, idx: number) => (
                <li key={step.id} className="workflow-step type-agent">
                  <span className="workflow-idx">{idx + 1}</span>
                  <div>
                    <strong>{step.title}</strong>
                    <em>{step.type}</em>
                  </div>
                </li>
              ))}
            </ol>
            <p className="hint" style={{ marginTop: "0.75rem" }}>
              Run from a ticket detail page: Engineer resolve note → AI Verify → customer email → close → store embedding.
            </p>
          </section>
        )}
      </div>
    </div>
  );
}
