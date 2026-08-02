import { FormEvent, useState } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

export default function LoginPage() {
  const { login, token, ready } = useAuth();
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("admin123");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  if (!ready) return <p className="page">Checking session…</p>;
  if (token) return <Navigate to="/" replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await login(email, password);
    } catch (err: any) {
      setError(err.message || "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page" role="main">
      <form className="login-panel" onSubmit={onSubmit} aria-label="Sign in">
        <p className="eyebrow">Enterprise AIOps</p>
        <h1>ServiceNow Agentic AI</h1>
        <p className="lede">Master-agent orchestration for triage, SLA, and CI root-cause analysis.</p>
        <label>
          Email
          <input value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label>
          Password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        {error && <p className="error">{error}</p>}
        <button disabled={loading}>{loading ? "Signing in…" : "Sign in"}</button>
        <p className="hint">Demo: admin@example.com / admin123</p>
      </form>
    </div>
  );
}
