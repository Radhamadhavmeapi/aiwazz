// /admin: the SaaS back office (content/ADMIN-PANEL.md). Its own lazy-loaded bundle; every permission is enforced by
// the API (this UI only hides what the role can't use). Non-staff get the same redirect as any unknown route.
import { lazy, Suspense, type ComponentType } from "react";
import { Navigate, Route, Routes } from "react-router";
import { ErrorState } from "./components/page";
import { StepUpDialog } from "./components/stepup-dialog";
import { AdminProvider, useAdmin } from "./lib/admin-context";
import { ADMIN_ITEMS } from "./nav";
import { SetupScreen, VerifyScreen } from "./pages/lock";

const PAGES: Record<string, ComponentType> = {
  "": lazy(() => import("./pages/overview")),
  audit: lazy(() => import("./pages/audit")),
  settings: lazy(() => import("./pages/settings")),
  users: lazy(() => import("./pages/users-routes")),
  invites: lazy(() => import("./pages/invites")),
  subscriptions: lazy(() => import("./pages/subscriptions")),
  payments: lazy(() => import("./pages/payments")),
  invoices: lazy(() => import("./pages/invoices")),
  plans: lazy(() => import("./pages/plans")),
  coupons: lazy(() => import("./pages/coupons")),
  support: lazy(() => import("./pages/support")),
  moderation: lazy(() => import("./pages/moderation")),
  voices: lazy(() => import("./pages/voices")),
  pronunciations: lazy(() => import("./pages/pronunciations")),
  api: lazy(() => import("./pages/api")),
  queue: lazy(() => import("./pages/queue")),
  health: lazy(() => import("./pages/health")),
  logs: lazy(() => import("./pages/logs")),
  email: lazy(() => import("./pages/email")),
  announcements: lazy(() => import("./pages/announcements")),
  compliance: lazy(() => import("./pages/compliance")),
  team: lazy(() => import("./pages/team")),
  analytics: lazy(() => import("./pages/analytics")),
};


function Gate() {
  const { state, can } = useAdmin();
  if (state.status === "loading") return <div className="min-h-dvh bg-background" aria-busy="true" />;
  if (state.status === "notfound") return <Navigate to="/" replace />;
  if (state.status === "error")
    return <div className="grid min-h-dvh place-items-center"><ErrorState message="Couldn't reach the server." onRetry={() => location.reload()} /></div>;
  const { me } = state;
  if (!me.mfa.enrolled) return <SetupScreen />;
  if (!me.mfa.unlocked) return <VerifyScreen />;
  const first = ADMIN_ITEMS.find((i) => can(i.perm));
  return (
    <Suspense fallback={<div className="min-h-dvh bg-background" />}>
      <Routes>
        {ADMIN_ITEMS.filter((i) => can(i.perm)).map((i) => {
          const Page = PAGES[i.to];
          return <Route key={i.to} path={i.to === "" ? "/" : `${i.to}/*`} element={Page ? <Page /> : <Navigate to="/admin" replace />} />;
        })}
        <Route path="*" element={<Navigate to={first ? `/admin/${first.to}` : "/"} replace />} />
      </Routes>
      <StepUpDialog />
    </Suspense>
  );
}

export default function AdminApp() {
  return (
    <AdminProvider>
      <Gate />
    </AdminProvider>
  );
}
