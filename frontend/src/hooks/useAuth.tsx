import React, { createContext, useContext, useEffect, useState } from "react";
import { api } from "../services/api";

type User = { id: string; email: string; full_name: string; role: string };

type AuthCtx = {
  user: User | null;
  token: string | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
};

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(localStorage.getItem("token"));
  const [ready, setReady] = useState(!localStorage.getItem("token"));

  useEffect(() => {
    function onCleared() {
      setToken(null);
      setUser(null);
      setReady(true);
    }
    window.addEventListener("aiops:auth-cleared", onCleared);
    return () => window.removeEventListener("aiops:auth-cleared", onCleared);
  }, []);

  useEffect(() => {
    if (!token) {
      setUser(null);
      setReady(true);
      return;
    }
    let cancelled = false;
    setReady(false);
    api
      .me()
      .then((u) => {
        if (!cancelled) {
          setUser(u);
          setReady(true);
        }
      })
      .catch(() => {
        if (!cancelled) {
          localStorage.removeItem("token");
          setToken(null);
          setUser(null);
          setReady(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  async function login(email: string, password: string) {
    const res = await api.login(email, password);
    localStorage.setItem("token", res.access_token);
    setToken(res.access_token);
    setUser(await api.me());
    setReady(true);
  }

  function logout() {
    localStorage.removeItem("token");
    setToken(null);
    setUser(null);
    setReady(true);
  }

  return <Ctx.Provider value={{ user, token, ready, login, logout }}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("AuthProvider missing");
  return ctx;
}
