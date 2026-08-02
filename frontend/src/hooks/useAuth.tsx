import React, { createContext, useContext, useEffect, useState } from "react";
import { api } from "../services/api";

type User = { id: string; email: string; full_name: string; role: string };

type AuthCtx = {
  user: User | null;
  token: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
};

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(localStorage.getItem("token"));

  useEffect(() => {
    if (!token) return;
    api.me().then(setUser).catch(() => {
      localStorage.removeItem("token");
      setToken(null);
    });
  }, [token]);

  async function login(email: string, password: string) {
    const res = await api.login(email, password);
    localStorage.setItem("token", res.access_token);
    setToken(res.access_token);
    setUser(await api.me());
  }

  function logout() {
    localStorage.removeItem("token");
    setToken(null);
    setUser(null);
  }

  return <Ctx.Provider value={{ user, token, login, logout }}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("AuthProvider missing");
  return ctx;
}
