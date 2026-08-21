import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

export interface AuthUser {
  username: string;
  role: string;
}

interface AuthStatus {
  enabled: boolean;
  authenticated: boolean;
  user: AuthUser | null;
}

interface AuthContextValue extends AuthStatus {
  loading: boolean;
  refresh: () => Promise<void>;
  login: (username: string, password: string, remember: boolean) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

async function readJson(response: Response) {
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(body?.detail || "请求失败，请稍后重试");
  }
  return body;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>({
    enabled: false,
    authenticated: false,
    user: null,
  });
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const response = await fetch("/api/auth/status", { credentials: "same-origin" });
      setStatus(await readJson(response));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh().catch(() => setLoading(false));
  }, [refresh]);

  const login = useCallback(async (username: string, password: string, remember: boolean) => {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password, remember }),
    });
    const body = await readJson(response);
    setStatus({ enabled: true, authenticated: true, user: body.user });
  }, []);

  const logout = useCallback(async () => {
    const response = await fetch("/api/auth/logout", {
      method: "POST",
      credentials: "same-origin",
    });
    await readJson(response);
    setStatus((current) => ({ ...current, authenticated: false, user: null }));
  }, []);

  const value = useMemo(() => ({ ...status, loading, refresh, login, logout }), [status, loading, refresh, login, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
