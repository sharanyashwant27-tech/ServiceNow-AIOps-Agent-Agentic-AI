import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../services/api";

function stackHref(component: string): string {
  const c = component.toLowerCase();
  if (c.includes("frontend") || c.includes("react") || c.includes("portal")) return "/";
  if (c.includes("vector") || c.includes("qdrant") || c.includes("rag") || c.includes("neo4j") || c.includes("graph")) {
    return "/knowledge";
  }
  if (c.includes("n8n") || c.includes("workflow") || c.includes("agent") || c.includes("llm") || c.includes("crew")) {
    return "/automation";
  }
  if (c.includes("servicenow") || c.includes("postgres") || c.includes("database")) return "/tickets";
  if (c.includes("monitor") || c.includes("prometheus") || c.includes("grafana")) return "/";
  return "/architecture";
}

export default function StackPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<any[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api.techStack()
      .then((r) => setItems(r.components || []))
      .catch((e) => setError(e.message));
  }, []);

  return (
    <div className="page">
      <header className="page-header">
        <h1>Technology stack</h1>
        <p>Click a row to open the related page in the portal.</p>
      </header>
      {error && <p className="error">{error}</p>}
      <section className="panel">
        <table className="table">
          <thead>
            <tr>
              <th>Component</th>
              <th>Technology</th>
              <th>Runtime</th>
            </tr>
          </thead>
          <tbody>
            {items.map((c) => (
              <tr
                key={c.component}
                className="clickable-row"
                onClick={() => navigate(stackHref(c.component || c.technology || ""))}
              >
                <td>{c.component}</td>
                <td>{c.technology}</td>
                <td>
                  {c.status ||
                    c.selected ||
                    c.provider ||
                    c.backend ||
                    (c.configured === true
                      ? "configured"
                      : c.configured === false
                        ? "fallback/local"
                        : JSON.stringify(
                            Object.fromEntries(
                              Object.entries(c).filter(([k]) => !["component", "technology"].includes(k))
                            )
                          ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
