import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import ClickableCard from "../components/ClickableCard";
import { api } from "../services/api";

export default function KnowledgePage() {
  const [q, setQ] = useState("Outlook is not opening after update");
  const [ci, setCi] = useState("Storage-D");
  const [pipelineDef, setPipelineDef] = useState<any>(null);
  const [graphPipelineDef, setGraphPipelineDef] = useState<any>(null);
  const [rag, setRag] = useState<any>(null);
  const [graph, setGraph] = useState<any>(null);
  const [running, setRunning] = useState(false);
  const [graphRunning, setGraphRunning] = useState(false);

  useEffect(() => {
    Promise.all([api.ragPipelineDefinition(), api.graphRagPipelineDefinition()])
      .then(([ragDef, graphDef]) => {
        setPipelineDef(ragDef);
        setGraphPipelineDef(graphDef);
      })
      .catch(console.error);
  }, []);

  async function runPipeline(e: FormEvent) {
    e.preventDefault();
    setRunning(true);
    try {
      setRag(await api.ragPipeline(q));
    } finally {
      setRunning(false);
    }
  }

  async function runGraphPipeline(e: FormEvent) {
    e.preventDefault();
    setGraphRunning(true);
    try {
      setGraph(await api.graphRagPipeline(ci, `${ci} failure reported on ticket`));
    } finally {
      setGraphRunning(false);
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <h1>RAG & GraphRAG Pipelines</h1>
        <p>Resolution retrieval (RAG) and CI impact / RCA analysis (GraphRAG).</p>
      </header>

      <div className="grid-2" style={{ marginBottom: "1rem" }}>
        {pipelineDef && (
          <section className="panel workflow-panel" style={{ maxWidth: "100%" }}>
            <h2>{pipelineDef.name}</h2>
            <ol className="workflow-flow rag-flow">
              {pipelineDef.steps.map((step: any, idx: number) => (
                <li key={step.id}>
                  <ClickableCard to="/knowledge" className="workflow-step type-agent" title={step.title}>
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
        )}
        {graphPipelineDef && (
          <section className="panel workflow-panel" style={{ maxWidth: "100%" }}>
            <h2>{graphPipelineDef.name}</h2>
            <ol className="workflow-flow rag-flow">
              {graphPipelineDef.steps.map((step: any, idx: number) => (
                <li key={step.id}>
                  <ClickableCard to="/knowledge" className="workflow-step type-orchestrator" title={step.title}>
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
        )}
      </div>

      <div className="grid-2">
        <section className="panel">
          <h2>Run RAG Pipeline</h2>
          <form className="inline-form" onSubmit={runPipeline}>
            <input value={q} onChange={(e) => setQ(e.target.value)} />
            <button disabled={running}>{running ? "Running…" : "Run pipeline"}</button>
          </form>

          {rag && (
            <>
              <h3 style={{ marginTop: "1rem" }}>Pipeline trace</h3>
              <ul className="workflow-trace">
                {(rag.trace || []).map((s: any) => (
                  <li key={s.id}>
                    <span>{s.title}</span>
                    <span className="ok">{s.detail || s.status}</span>
                  </li>
                ))}
              </ul>
              <div className="ai-summary-card" style={{ marginTop: "1rem" }}>
                <div className="ai-summary-head">
                  <strong>Final Resolution</strong>
                </div>
                <pre className="resolution-block">{rag.final_resolution || rag.answer}</pre>
              </div>
            </>
          )}
        </section>

        <section className="panel">
          <h2>Run GraphRAG Pipeline</h2>
          <form className="inline-form" onSubmit={runGraphPipeline}>
            <input value={ci} onChange={(e) => setCi(e.target.value)} placeholder="Storage-D" />
            <button disabled={graphRunning}>{graphRunning ? "Running…" : "Run pipeline"}</button>
          </form>

          {graph && (
            <>
              <h3 style={{ marginTop: "1rem" }}>Pipeline trace</h3>
              <ul className="workflow-trace">
                {(graph.trace || []).map((s: any) => (
                  <li key={s.id}>
                    <span>{s.title}</span>
                    <span className="ok">{s.detail || s.status}</span>
                  </li>
                ))}
              </ul>

              <dl className="kv" style={{ marginTop: "1rem" }}>
                <div>
                  <dt>Related CI</dt>
                  <dd>{graph.related_ci || graph.configuration_item}</dd>
                </div>
                <div>
                  <dt>Dependencies</dt>
                  <dd>{(graph.dependencies || []).join(" → ") || "—"}</dd>
                </div>
                <div>
                  <dt>Impact chain</dt>
                  <dd>{(graph.impact_chain || graph.impact_analysis?.impact_chain || []).join(" → ") || "—"}</dd>
                </div>
                <div>
                  <dt>Affected services</dt>
                  <dd>{(graph.affected_services || graph.blast_radius || []).join(", ") || "—"}</dd>
                </div>
                <div>
                  <dt>Severity</dt>
                  <dd>{graph.impact_analysis?.severity || graph.severity || "—"}</dd>
                </div>
                <div>
                  <dt>Backend</dt>
                  <dd>{graph.backend}</dd>
                </div>
              </dl>

              <h3 style={{ marginTop: "1rem" }}>Previous failures</h3>
              <ul className="list compact">
                {(graph.previous_failures || []).map((f: any) => (
                  <li key={f.id}>
                    <ClickableCard
                      to={f.ticket_id ? `/tickets/${f.ticket_id}` : "/tickets"}
                      className="list-card-link"
                      title="Open related tickets"
                    >
                      <div>
                        <strong>
                          {f.title} ({Math.round((f.score || 0) * 100)}%)
                        </strong>
                        <span>{f.snippet}</span>
                      </div>
                    </ClickableCard>
                  </li>
                ))}
                {!graph.previous_failures?.length && (
                  <li>
                    <div>
                      <span>None found</span>
                    </div>
                  </li>
                )}
              </ul>
              <p className="hint">
                Related: <Link to="/tickets">Tickets</Link> · <Link to="/automation">Automation</Link>
              </p>

              <div className="ai-summary-card" style={{ marginTop: "1rem" }}>
                <div className="ai-summary-head">
                  <strong>Impact Analysis / RCA</strong>
                </div>
                <pre className="resolution-block">
                  {graph.rca || graph.root_cause_analysis || graph.root_cause_suggestion}
                </pre>
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
