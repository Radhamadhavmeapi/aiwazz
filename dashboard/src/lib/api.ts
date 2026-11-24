// Same-origin JSON client for /api. Cookie session + CSRF double-submit (X-CSRF-Token from the
// readable __Host-aiwazz_csrf cookie). API errors become ApiError with the server's message.
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public retryAfter?: number,
  ) {
    super(message);
  }
}

const CSRF_COOKIE = "__Host-aiwazz_csrf";
const readCookie = (name: string) =>
  document.cookie
    .split("; ")
    .find((c) => c.startsWith(`${name}=`))
    ?.slice(name.length + 1);

async function csrfToken(fresh = false): Promise<string> {
  const existing = readCookie(CSRF_COOKIE);
  if (existing && !fresh) return decodeURIComponent(existing);
  const r = await fetch("/api/auth/csrf", { credentials: "same-origin" });
  return (await r.json()).csrf_token as string;
}

function messageFrom(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown })?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg).replace(/^Value error, /, "");
  if (status === 429) return "Too many attempts. Please wait a moment.";
  if (status >= 500) return "Something went wrong on our side. Please try again.";
  return "Request failed";
}

export async function api<T = unknown>(path: string, init: { method?: string; json?: unknown } = {}, retried = false): Promise<T> {
  const method = init.method ?? (init.json !== undefined ? "POST" : "GET");
  const headers: Record<string, string> = { Accept: "application/json" };
  if (init.json !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["X-CSRF-Token"] = await csrfToken();

  let res: Response;
  try {
    res = await fetch(path, { method, headers, credentials: "same-origin", body: init.json !== undefined ? JSON.stringify(init.json) : undefined });
  } catch {
    throw new ApiError(0, "You seem to be offline. Check your connection and try again.");
  }
  const body = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) {
    const msg = messageFrom(body, res.status);
    // Stale CSRF cookie (e.g. after the session rotated it in another tab): refresh once and retry.
    if (res.status === 403 && msg.includes("CSRF") && !retried) {
      await csrfToken(true);
      return api<T>(path, init, true);
    }
    throw new ApiError(res.status, msg, Number(res.headers.get("retry-after")) || undefined);
  }
  return body as T;
}

/** POST JSON, get binary audio back (e.g. the pronunciation ▶ test). Same CSRF + error handling as api(). */
export async function apiAudio(path: string, json: unknown): Promise<Blob> {
  let res: Response;
  try {
    res = await fetch(path, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": await csrfToken() },
      body: JSON.stringify(json),
    });
  } catch {
    throw new ApiError(0, "You seem to be offline. Check your connection and try again.");
  }
  if (!res.ok) throw new ApiError(res.status, messageFrom(await res.json().catch(() => null), res.status));
  return res.blob();
}
