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
import ClickableCard from "../components/ClickableCard";
import { DASHBOARD_CARD_HREFS, DASHBOARD_CHART_HREFS } from "../nav/cardLinks";
import { api } from "../services/api";

const COLORS = ["#0f6e56", "#c45d26", "#1f4b7a", "#8a6d3b", "#5b4b8a", "#7a3b4b", "#2f6f8f"];

const CARD_TONES: Record<string, string> = {
  open_tickets: "tone-neutral",
  p1_tickets: "tone-critical",
  p2_tickets: "tone-major",
  p3_tickets: "tone-minor",
  resolved_today: "tone-good",
  sla_breaches: "tone-critical",
  average_resolution_time: "tone-neutral",
  agent_performance: "tone-ai",
};

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
            to={DASHBOARD_CARD_HREFS[card.id] || "/tickets"}
            className={`dash-card ${CARD_TONES[card.id] || "tone-neutral"}`}
            title={`Open ${card.title}`}
          >
            <span>{card.title}</span>
            <strong>{card.value}</strong>
          </ClickableCard>
        ))}
      </section>

      <h2 className="section-title">Charts</h2>
      <div className="grid-2">
        <ChartPanel chartId="ticket_trend" title="Ticket Trend">
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={ticketTrend}>
              <CartesianGrid strokeDasharray="3 3" stroke="#d7d2c8" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Area type="monotone" dataKey="created" name="Created" stroke="#1f4b7a" fill="#c5d5ea" />
            </AreaChart>
          </ResponsiveContainer>
        </ChartPanel>

        <ChartPanel chartId="resolution_trend" title="Resolution Trend">
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={resolutionTrend}>
              <CartesianGrid strokeDasharray="3 3" stroke="#d7d2c8" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Line type="monotone" dataKey="resolved" name="Resolved" stroke="#0f6e56" strokeWidth={2} />
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
              <CartesianGrid strokeDasharray="3 3" stroke="#d7d2c8" />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Legend />
              <Bar dataKey="workload" name="Workload" fill="#c45d26" radius={[4, 4, 0, 0]} />
              <Bar dataKey="capacity" name="Capacity" fill="#9bb0c4" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartPanel>

        <ChartPanel chartId="sla_compliance" title="SLA Compliance">
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie data={slaCompliance} dataKey="value" nameKey="name" outerRadius={90} label>
                {slaCompliance.map((row: any, i: number) => (
                  <Cell key={i} fill={row.name === "Breached" ? "#c45d26" : "#0f6e56"} />
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
              <CartesianGrid strokeDasharray="3 3" stroke="#d7d2c8" />
              <XAxis type="number" allowDecimals={false} />
              <YAxis type="category" dataKey="name" width={110} tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="value" name="Documents" fill="#5b4b8a" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartPanel>

        <ChartPanel chartId="ai_confidence_scores" title="AI Confidence Scores">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={aiConfidence}>
              <CartesianGrid strokeDasharray="3 3" stroke="#d7d2c8" />
              <XAxis dataKey="name" tick={{ fontSize: 10 }} />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="value" name="Tickets" fill="#1f4b7a" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartPanel>

        <ChartPanel chartId="ai_confidence_by_agent" title="AI Confidence by Agent">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={aiByAgent}>
              <CartesianGrid strokeDasharray="3 3" stroke="#d7d2c8" />
              <XAxis dataKey="name" tick={{ fontSize: 10 }} />
              <YAxis domain={[0, 100]} />
              <Tooltip />
              <Bar dataKey="confidence" name="Avg %" fill="#0f6e56" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartPanel>
      </div>
    </div>
  );
}
