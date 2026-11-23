import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import { PreviewPlayerProvider } from "@/components/audio/preview-player";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ThemeProvider } from "@/lib/theme";

const PreviewIndex = lazy(() => import("@/pages/preview-index"));
const TokensPage = lazy(() => import("@/pages/tokens"));
const GeneratePage = lazy(() => import("@/pages/generate"));
const AuthPage = lazy(() => import("@/pages/auth"));
const Placeholder = lazy(() => import("@/pages/placeholder"));

// Preview routes. Deep links work on static hosting because the build copies
// index.html into each route folder (see tools/deploy-preview.sh).
export const ROUTES = ["tokens", "generate", "login", "signup", "history", "voices", "api-keys", "settings"];

export default function App() {
  return (
    <ThemeProvider>
      <TooltipProvider delayDuration={300}>
        <PreviewPlayerProvider>
          <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, "")}>
            <Suspense fallback={<div className="min-h-dvh bg-background" />}>
              <Routes>
                <Route path="/" element={<PreviewIndex />} />
                <Route path="/tokens" element={<TokensPage />} />
                <Route path="/generate" element={<GeneratePage />} />
                <Route path="/login" element={<AuthPage mode="login" />} />
                <Route path="/signup" element={<AuthPage mode="signup" />} />
                {["history", "voices", "api-keys", "settings"].map((p) => (
                  <Route key={p} path={`/${p}`} element={<Placeholder page={p} />} />
                ))}
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </Suspense>
          </BrowserRouter>
        </PreviewPlayerProvider>
      </TooltipProvider>
      <Toaster position="bottom-right" richColors={false} closeButton />
    </ThemeProvider>
  );
}
