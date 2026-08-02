import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./hooks/useAuth";
import AppShell from "./layouts/AppShell";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import TicketsPage from "./pages/TicketsPage";
import TicketDetailPage from "./pages/TicketDetailPage";
import KnowledgePage from "./pages/KnowledgePage";
import WorkloadPage from "./pages/WorkloadPage";
import AutomationPage from "./pages/AutomationPage";
import StackPage from "./pages/StackPage";
import ArchitecturePage from "./pages/ArchitecturePage";
import WorkflowPage from "./pages/WorkflowPage";

function Private({ children }: { children: React.ReactNode }) {
  const { token } = useAuth();
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <Private>
            <AppShell />
          </Private>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="tickets" element={<TicketsPage />} />
        <Route path="tickets/:id" element={<TicketDetailPage />} />
        <Route path="knowledge" element={<KnowledgePage />} />
        <Route path="workload" element={<WorkloadPage />} />
        <Route path="automation" element={<AutomationPage />} />
        <Route path="stack" element={<StackPage />} />
        <Route path="architecture" element={<ArchitecturePage />} />
        <Route path="workflow" element={<WorkflowPage />} />
      </Route>
    </Routes>
  );
}
