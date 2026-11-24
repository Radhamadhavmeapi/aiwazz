import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router";
import { api } from "./api";
import { PREVIEW } from "./env";

export type User = { id: number; email: string; role: "admin" | "user"; plan?: string; plan_until?: string | null; api_access?: boolean; created_at: string; via: string };
type State = { status: "loading" } | { status: "anon" } | { status: "authed"; user: User };
type Ctx = {
  state: State;
  user: User | null;
  login: (email: string, password: string) => Promise<User>;
  signup: (email: string, password: string, inviteCode: string, marketing?: boolean) => Promise<User>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<Ctx | null>(null);
const PREVIEW_USER: User = { id: 0, email: "preview@aiwazz.in", role: "admin", created_at: "", via: "session" };
const mockDelay = <T,>(v: T) => new Promise<T>((r) => setTimeout(() => r(v), 900));

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>(PREVIEW ? { status: "authed", user: PREVIEW_USER } : { status: "loading" });

  useEffect(() => {
    if (PREVIEW) return;
    api<{ user: User | null }>("/api/auth/session").then(
      ({ user }) => setState(user ? { status: "authed", user } : { status: "anon" }),
      () => setState({ status: "anon" }),
    );
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    if (PREVIEW) return mockDelay(PREVIEW_USER);
    const user = await api<User>("/api/auth/login", { json: { email, password } });
    setState({ status: "authed", user });
    return user;
  }, []);
  const signup = useCallback(async (email: string, password: string, invite_code: string, marketing = false) => {
    if (PREVIEW) return mockDelay(PREVIEW_USER);
    const user = await api<User>("/api/auth/signup", { json: { email, password, invite_code, accept_terms: true, marketing_opt_in: marketing } });
    setState({ status: "authed", user });
    return user;
  }, []);
  const logout = useCallback(async () => {
    if (PREVIEW) return;
    try {
      await api("/api/auth/logout", { method: "POST" });
    } finally {
      setState({ status: "anon" });
    }
  }, []);

  return (
    <AuthContext.Provider value={{ state, user: state.status === "authed" ? state.user : null, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

/** Full-screen neutral placeholder while the session is checked (no flash of the login page). */
function Splash() {
  return <div className="min-h-dvh bg-background" aria-busy="true" />;
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { state } = useAuth();
  const loc = useLocation();
  if (state.status === "loading") return <Splash />;
  if (state.status === "anon") return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />;
  return children;
}

export function GuestOnly({ children }: { children: ReactNode }) {
  const { state } = useAuth();
  if (state.status === "loading") return <Splash />;
  if (state.status === "authed") return <Navigate to="/generate" replace />;
  return children;
}

/** Only allow in-app redirect targets after login (no open redirects). */
export function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\") ? next : "/generate";
}
