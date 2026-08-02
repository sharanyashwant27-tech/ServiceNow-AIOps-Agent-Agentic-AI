import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

const links = [
  ["/", "Ticket Dashboard"],
  ["/tickets", "Tickets"],
  ["/workload", "Workload"],
  ["/knowledge", "Knowledge & Graph"],
  ["/automation", "AI Automation"],
  ["/stack", "Tech Stack"],
  ["/architecture", "Architecture"],
  ["/workflow", "Workflow & Status"],
];

export default function AppShell() {
  const { user, logout } = useAuth();
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">AIOps</span>
          <span className="brand-sub">ServiceNow Agentic</span>
        </div>
        <nav>
          {links.map(([to, label]) => (
            <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => (isActive ? "nav active" : "nav")}>
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="user">{user?.full_name}</div>
          <button className="ghost" onClick={logout}>
            Sign out
          </button>
        </div>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
