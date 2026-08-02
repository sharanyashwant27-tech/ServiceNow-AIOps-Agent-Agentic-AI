import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import ClickableCard from "../components/ClickableCard";
import { api } from "../services/api";

export default function WorkloadPage() {
  const [engineers, setEngineers] = useState<any[]>([]);

  useEffect(() => {
    api.engineers().then(setEngineers).catch(console.error);
  }, []);

  const chart = engineers.map((e) => ({
    name: e.name.split(" ")[0],
    workload: e.current_workload,
    capacity: e.max_workload,
  }));

  return (
    <div className="page">
      <header className="page-header">
        <h1>Engineer workload</h1>
        <p>Click an engineer card to see their assigned tickets.</p>
      </header>
      <section className="panel">
        <ClickableCard to="/tickets?status=open" className="panel-link-header" title="Open tickets">
          <h2>Capacity chart</h2>
          <span className="panel-link-cta">Tickets →</span>
        </ClickableCard>
        <div className="chart">
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={chart}>
              <CartesianGrid strokeDasharray="3 3" stroke="#b7d4ea" />
              <XAxis dataKey="name" />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="workload" fill="#ff5a7a" radius={[4, 4, 0, 0]} />
              <Bar dataKey="capacity" fill="#00b4a0" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <ul className="list">
          {engineers.map((e) => (
            <li key={e.id}>
              <ClickableCard to={`/tickets?assigned=${encodeURIComponent(e.email)}`} className="list-card-link">
                <div>
                  <strong>
                    {e.name} · {e.assignment_group}
                  </strong>
                  <span>{e.skills.join(", ")}</span>
                </div>
                <em>
                  {e.current_workload}/{e.max_workload}
                </em>
              </ClickableCard>
            </li>
          ))}
        </ul>
        <p className="hint">
          See also <Link to="/automation">AI Automation</Link> for assignment agent runs.
        </p>
      </section>
    </div>
  );
}
