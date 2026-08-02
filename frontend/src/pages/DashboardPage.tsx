import { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Link } from "react-router-dom";
import ClickableCard from "../components/ClickableCard";
import { DASHBOARD_CARD_HREFS, DASHBOARD_CHART_HREFS } from "../nav/cardLinks";
import { api } from "../services/api";
import {
  formatDateShort,
  ticketAssignment,
  ticketCompletedAt,
  ticketCreatedAt,
  ticketStatus,
} from "../utils/dates";

const COLORS = ["#00b4a0", "#ff5a7a", "#0088cc", "#ff9f1c", "#12b76a", "#0ea5e9", "#e11d48"];

const CARD_TONES: Record<string, string> = {
  tickets_created: "tone-ai",
  open_tickets: "tone-neutral",
  p1_tickets: "tone-critical",
  p2_tickets: "tone-major",
  p3_tickets: "tone-minor",
  priority_p1: "tone-critical",
  priority_p2: "tone-major",
  priority_p3: "tone-minor",
  resolved_today: "tone-good",
  sla_breaches: "tone-critical",
  average_resolution_time: "tone-neutral",
  agent_performance: "tone-ai",
  status_new: "tone-neutral",
  status_assigned: "tone-minor",
  status_work_in_progress: "tone-major",
  status_waiting_for_customer: "tone-major",
  status_resolved: "tone-good",
  status_completed: "tone-good",
  status_closed: "tone-neutral",
};

function cardHref(card: { id?: string; kind?: string; filter?: string; title?: string }): string {
  if (card.id && DASHBOARD_CARD_HREFS[card.id]) return DASHBOARD_CARD_HREFS[card.id];
  if (card.kind === "status" && card.filter) {
    return `/tickets?state=${encodeURIComponent(card.filter)}`;
  }
  if (card.kind === "priority" && card.filter) {
    return `/tickets?priority=${encodeURIComponent(card.filter)}`;
  }
  return "/tickets";
}

function shortDate(iso: string) {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function ChartPanel({
  chartId,
  title,
  children,
}: {
  chartId: string;
  title: string;
  children: React.ReactNode;
}) {
  const to = DASHBOARD_CHART_HREFS[chartId] || "/tickets";
  return (
    <section className="panel">
      <ClickableCard to={to} className="panel-link-header" title={`Open ${title}`}>
        <h2>{title}</h2>
        <span className="panel-link-cta">View →</span>
      </ClickableCard>
      <div className="chart">{children}</div>
    </section>
  );
}

export default function DashboardPage() {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.dashboard().then(setData).catch((e) => setError(e.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!data) return <p>Loading dashboards…</p>;

  const cards = data.ticket_dashboard?.cards || [];
  const statusCards = data.ticket_dashboard?.status_cards || [];
  const priorityCards = data.ticket_dashboard?.priority_cards || [];
  const matrix = data.ticket_dashboard?.status_priority_matrix || [];
  const recentTickets = data.ticket_dashboard?.recent_tickets || [];
  const ticketsCreated = data.ticket_dashboard?.tickets_created ?? cards.find((c: any) => c.id === "tickets_created")?.value ?? "—";
  const charts = data.charts || data.ticket_dashboard?.charts || {};

  const ticketTrend = (charts.ticket_trend || []).map((r: any) => ({
    ...r,
    label: shortDate(r.date),
  }));
  const resolutionTrend = (charts.resolution_trend || []).map((r: any) => ({
    ...r,
    label: shortDate(r.date),
  }));
  const categoryDistribution = charts.category_distribution || [];
  const engineerWorkload = charts.engineer_workload || [];
  const slaCompliance = charts.sla_compliance || [];
  const kbUsage = charts.knowledge_base_usage || [];
  const aiConfidence = charts.ai_confidence_scores || [];
  const aiByAgent = charts.ai_confidence_by_agent || [];

  return (
    <div className="page">
      <header className="page-header">
        <h1>Ticket Dashboard</h1>
        <p>Click any card or chart to open its page. Filters apply on Tickets where relevant.</p>
      </header>

      <section className="dashboard-cards">
        {cards.map((card: any) => (
          <ClickableCard
            key={card.id}
            to={cardHref(card)}
            className={`dash-card ${CARD_TONES[card.id] || "tone-neutral"}`}
            title={`Open ${card.title}`}
          >
            <span>{card.title}</span>
            <strong>{card.value}</strong>
          </ClickableCard>
        ))}
      </section>

      <h2 className="section-title">Tickets created · {ticketsCreated}</h2>
      <p className="hint" style={{ marginTop: "-0.35rem" }}>
        Counts for every status and priority across all created tickets.
      </p>

      <h3 className="subsection-title">By status</h3>
      <section className="dashboard-cards status-cards">
        {statusCards.map((card: any) => (
          <ClickableCard
            key={card.id}
            to={cardHref(card)}
            className={`dash-card ${CARD_TONES[card.id] || "tone-neutral"}`}
            title={`Tickets in ${card.title}`}
          >
            <span>{card.title}</span>
            <strong>{card.value}</strong>
          </ClickableCard>
        ))}
        {!statusCards.length && <p className="hint">No status counts yet.</p>}
      </section>

      <h3 className="subsection-title">By priority</h3>
      <section className="dashboard-cards priority-cards">
        {priorityCards.map((card: any) => (
          <ClickableCard
            key={card.id}
            to={cardHref(card)}
            className={`dash-card ${CARD_TONES[card.id] || "tone-neutral"}`}
            title={`${card.title}`}
          >
            <span>{card.title}</span>
            <strong>{card.value}</strong>
          </ClickableCard>
        ))}
      </section>

      {matrix.length > 0 && (
        <section className="panel" style={{ marginBottom: "1rem" }}>
          <ClickableCard to="/tickets" className="panel-link-header" title="Open Tickets">
            <h2>Status × Priority</h2>
            <span className="panel-link-cta">View →</span>
          </ClickableCard>
          <table className="table">
            <thead>
              <tr>
                <th>Status</th>
                <th>P1</th>
                <th>P2</th>
                <th>P3</th>
                <th>Total</th>
              </tr>
            </thead>
            <tbody>
              {matrix.map((row: any) => (
                <tr key={row.status}>
                  <td>{row.status}</td>
                  <td>{row.P1}</td>
                  <td>{row.P2}</td>
                  <td>{row.P3}</td>
                  <td>
                    <strong>{row.total}</strong>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <section className="panel" style={{ marginBottom: "1rem" }}>
        <ClickableCard to="/tickets" className="panel-link-header" title="Open Tickets">
          <h2>Recent tickets</h2>
          <span className="panel-link-cta">View all →</span>
        </ClickableCard>
        <table className="table tickets-table">
          <thead>
            <tr>
              <th>Number</th>
              <th>Title</th>
              <th>Status</th>
              <th>Priority</th>
              <th>Assignment</th>
              <th>Created</th>
              <th>Completed</th>
            </tr>
          </thead>
          <tbody>
            {recentTickets.map((t: any) => (
              <tr key={t.id}>
                <td>
                  <Link to={`/tickets/${t.id}`}>{t.number}</Link>
                </td>
                <td>{t.title}</td>
                <td>
                  <span className="status-chip">{ticketStatus(t)}</span>
                </td>
                <td>
                  <span className={`pill p-${t.priority}`}>{t.priority}</span>
                </td>
                <td>{ticketAssignment(t)}</td>
                <td>{formatDateShort(ticketCreatedAt(t))}</td>
                <td>{formatDateShort(ticketCompletedAt(t))}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!recentTickets.length && <p className="hint">No tickets created yet.</p>}
      </section>

      <h2 className="section-title">Charts</h2>
      <div className="grid-2">
        <ChartPanel chartId="ticket_trend" title="Ticket Trend">
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={ticketTrend}>
              <CartesianGrid strokeDasharray="3 3" stroke="#b7d4ea" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Area type="monotone" dataKey="created" name="Created" stroke="#0088cc" fill="#9fe0ff" />
            </AreaChart>
          </ResponsiveContainer>
        </ChartPanel>

        <ChartPanel chartId="resolution_trend" title="Resolution Trend">
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={resolutionTrend}>
              <CartesianGrid strokeDasharray="3 3" stroke="#b7d4ea" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Line type="monotone" dataKey="resolved" name="Resolved" stroke="#12b76a" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </ChartPanel>

        <ChartPanel chartId="category_distribution" title="Category Distribution">
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie data={categoryDistribution} dataKey="value" nameKey="name" outerRadius={90} label>
                {categoryDistribution.map((_: any, i: number) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </ChartPanel>

        <ChartPanel chartId="engineer_workload" title="Engineer Workload">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={engineerWorkload}>
              <CartesianGrid strokeDasharray="3 3" stroke="#b7d4ea" />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Legend />
              <Bar dataKey="workload" name="Workload" fill="#ff5a7a" radius={[4, 4, 0, 0]} />
              <Bar dataKey="capacity" name="Capacity" fill="#00b4a0" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartPanel>

        <ChartPanel chartId="sla_compliance" title="SLA Compliance">
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie data={slaCompliance} dataKey="value" nameKey="name" outerRadius={90} label>
                {slaCompliance.map((row: any, i: number) => (
                  <Cell key={i} fill={row.name === "Breached" ? "#e11d48" : "#12b76a"} />
                ))}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
          <p className="hint">Compliance {data.sla_compliance?.compliance_pct ?? "—"}%</p>
        </ChartPanel>

        <ChartPanel chartId="knowledge_base_usage" title="Knowledge Base Usage">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={kbUsage} layout="vertical" margin={{ left: 24 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#b7d4ea" />
              <XAxis type="number" allowDecimals={false} />
              <YAxis type="category" dataKey="name" width={110} tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="value" name="Documents" fill="#ff9f1c" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartPanel>

        <ChartPanel chartId="ai_confidence_scores" title="AI Confidence Scores">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={aiConfidence}>
              <CartesianGrid strokeDasharray="3 3" stroke="#b7d4ea" />
              <XAxis dataKey="name" tick={{ fontSize: 10 }} />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="value" name="Tickets" fill="#0088cc" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartPanel>

        <ChartPanel chartId="ai_confidence_by_agent" title="AI Confidence by Agent">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={aiByAgent}>
              <CartesianGrid strokeDasharray="3 3" stroke="#b7d4ea" />
              <XAxis dataKey="name" tick={{ fontSize: 10 }} />
              <YAxis domain={[0, 100]} />
              <Tooltip />
              <Bar dataKey="confidence" name="Avg %" fill="#00b4a0" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartPanel>
      </div>
    </div>
  );
}
