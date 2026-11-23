import { lazy, Suspense, type ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import { PreviewPlayerProvider } from "@/components/audio/preview-player";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider, GuestOnly, RequireAuth } from "@/lib/auth";
import { PREVIEW } from "@/lib/env";
import { ThemeProvider } from "@/lib/theme";

const PreviewIndex = lazy(() => import("@/pages/preview-index"));
const TokensPage = lazy(() => import("@/pages/tokens"));
const GeneratePage = lazy(() => import("@/pages/generate"));
const AuthPage = lazy(() => import("@/pages/auth"));
const Placeholder = lazy(() => import("@/pages/placeholder"));

// Static hosting: deep links work because nginx falls back to index.html (production) or because
// the preview build copies index.html into each route folder (tools/deploy-preview.sh).
export const ROUTES = ["tokens", "generate", "login", "signup", "history", "voices", "api-keys", "settings"];

const guard = (el: ReactNode) => (PREVIEW ? el : <RequireAuth>{el}</RequireAuth>);
const guest = (el: ReactNode) => (PREVIEW ? el : <GuestOnly>{el}</GuestOnly>);

export default function App() {
  return (
    <ThemeProvider>
      <TooltipProvider delayDuration={300}>
        <PreviewPlayerProvider>
          <AuthProvider>
            <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, "")}>
              <Suspense fallback={<div className="min-h-dvh bg-background" />}>
                <Routes>
                  <Route path="/" element={PREVIEW ? <PreviewIndex /> : <Navigate to="/generate" replace />} />
                  {PREVIEW && <Route path="/tokens" element={<TokensPage />} />}
                  <Route path="/generate" element={guard(<GeneratePage />)} />
                  <Route path="/login" element={guest(<AuthPage mode="login" />)} />
                  <Route path="/signup" element={guest(<AuthPage mode="signup" />)} />
                  {["history", "voices", "api-keys", "settings"].map((p) => (
                    <Route key={p} path={`/${p}`} element={guard(<Placeholder page={p} />)} />
                  ))}
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </Suspense>
            </BrowserRouter>
          </AuthProvider>
        </PreviewPlayerProvider>
      </TooltipProvider>
      <Toaster position="bottom-right" richColors={false} closeButton />
    </ThemeProvider>
  );
}
