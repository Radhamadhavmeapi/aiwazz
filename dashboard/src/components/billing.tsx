import { Check, Download, FileText, Loader2, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { api, ApiError } from "@/lib/api";
import { PREVIEW } from "@/lib/env";
import { fmtChars, refreshUsage, type Usage } from "@/lib/usage";
import { cn } from "@/lib/utils";

type Period = "monthly" | "yearly";
type Plan = { id: string; name: string; monthly: number; yearly: number; yearly_per_month: number; characters: number; total_monthly_paise: number; total_yearly_paise: number };
type Sub = {
  id: number; plan: string; period: Period; status: string; current_start: string | null; current_end: string | null; cancel_at_period_end: boolean;
  pending_plan?: string | null; pending_period?: Period | null;
};
type Profile = { name: string; gstin: string; state: string; address: string };
type Billing = {
  enabled: boolean;
  test_mode: boolean;
  gst_rate: number;
  plans: Plan[];
  subscription: Sub | null;
  profile: Profile;
  invoices: { id: number; number: string; issued_at: string; plan: string; period: Period; total_paise: number }[];
  states: { code: string; name: string }[];
};
type Checkout = { key_id: string; subscription_id: string; name: string; description: string; prefill: { email: string; name: string } };

const inr = (n: number) => `₹${n.toLocaleString("en-IN")}`;
const inrPaise = (p: number) => `₹${(p / 100).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const day = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString("en-IN", { dateStyle: "medium", timeZone: "Asia/Kolkata" }) : "–");
const ORDER = ["free", "starter", "creator", "pro"];

declare global {
  interface Window {
    Razorpay?: new (opts: Record<string, unknown>) => { open: () => void; on: (ev: string, cb: (r: unknown) => void) => void };
  }
}

function loadCheckout(): Promise<void> {
  if (window.Razorpay) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://checkout.razorpay.com/v1/checkout.js";
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("Couldn't load Razorpay. Check your connection or ad blocker."));
    document.head.appendChild(s);
  });
}

function ProfileForm({ b, onSaved, onCancel }: { b: Billing; onSaved: (p: Profile) => void; onCancel?: () => void }) {
  const [f, setF] = useState<Profile>(b.profile);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const set = (k: keyof Profile) => (v: string) => (setF((x) => ({ ...x, [k]: v })), setErr(null));
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const p = await api<Profile>("/api/billing/profile", { method: "PUT", json: f });
      toast.success("Billing details saved");
      onSaved(p);
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : "Couldn't save");
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={submit} className="space-y-4 rounded-xl border bg-surface-2/50 p-4">
      <p className="text-sm text-muted-foreground">Printed on your GST invoices. Add a GSTIN only if you want to claim input tax credit.</p>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="b-name">Name or business name</Label>
          <Input id="b-name" required minLength={2} maxLength={150} value={f.name} onChange={(e) => set("name")(e.target.value)} autoComplete="organization" />
        </div>
        <div className="space-y-2">
          <Label htmlFor="b-state">State</Label>
          <select
            id="b-state"
            required
            value={f.state}
            onChange={(e) => set("state")(e.target.value)}
            className="h-9 w-full rounded-lg border border-input bg-surface px-3 text-sm focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
          >
            <option value="">Select your state</option>
            {b.states.map((s) => (
              <option key={s.code} value={s.code}>
                {s.name}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="b-gstin">GSTIN (optional)</Label>
          <Input
            id="b-gstin"
            maxLength={15}
            value={f.gstin}
            onChange={(e) => set("gstin")(e.target.value.toUpperCase().replace(/\s/g, ""))}
            placeholder="27ABCDE1234F1Z5"
            className="font-mono uppercase"
          />
        </div>
        <div className="space-y-2 sm:col-span-2">
          <Label htmlFor="b-addr">Address {f.gstin ? "" : "(optional)"}</Label>
          <Textarea id="b-addr" rows={2} maxLength={300} value={f.address} onChange={(e) => set("address")(e.target.value)} autoComplete="street-address" />
        </div>
      </div>
      {err && (
        <p role="alert" className="text-sm text-danger">
          {err}
        </p>
      )}
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={busy}>
          {busy && <Loader2 className="animate-spin" />} Save details
        </Button>
        {onCancel && (
          <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
            Cancel
          </Button>
        )}
      </div>
    </form>
  );
}

export function BillingCard({ usage }: { usage: Usage | null }) {
  const [params, setParams] = useSearchParams();
  const [b, setB] = useState<Billing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [period, setPeriod] = useState<Period>(params.get("period") === "yearly" ? "yearly" : "monthly");
  const [editing, setEditing] = useState(false);
  const [pending, setPending] = useState<string | null>(null); // plan id waiting for billing details / checkout
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(() => {
    if (PREVIEW) return;
    api<Billing>("/api/billing").then(setB, (e) => setError(e instanceof ApiError ? e.message : "Couldn't load billing"));
  }, []);
  useEffect(load, [load]);

  // Arrived from the pricing page (?plan=creator&period=yearly): bring the card into view once.
  useEffect(() => {
    if (!b || !params.get("plan")) return;
    document.getElementById("billing")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [b, params]);

  const [coupon, setCoupon] = useState("");
  // Live subscription: upgrades apply now (Razorpay charges the prorated difference), downgrades at renewal.
  const changePlan = async (planId: string) => {
    setBusy(planId);
    try {
      const r = await api<{ applies: string; subscription: Sub }>("/api/billing/change-plan", { json: { plan: planId, period } });
      toast.success(r.applies === "now" ? "Plan changed" : "Change scheduled", {
        description: r.applies === "now" ? "Razorpay charges the prorated difference for this period." : "It starts on your next billing date.",
      });
      await load();
    } catch (e) {
      toast.error("Couldn't change the plan", { description: e instanceof ApiError ? e.message : undefined });
    } finally {
      setBusy(null);
    }
  };

  const pay = async (planId: string) => {
    if (!b) return;
    if (!b.profile.name || !b.profile.state) {
      setPending(planId);
      setEditing(true);
      return;
    }
    setBusy(planId);
    try {
      const co = await api<Checkout>("/api/billing/subscribe", { json: { plan: planId, period, coupon: coupon.trim() } });
      await loadCheckout();
      const rzp = new window.Razorpay!({
        key: co.key_id,
        subscription_id: co.subscription_id,
        name: co.name,
        description: co.description,
        prefill: co.prefill,
        theme: { color: "#2D36DB" },
        modal: { ondismiss: () => setBusy(null) },
        handler: async (r: Record<string, string>) => {
          try {
            await api("/api/billing/verify", { json: r });
            toast.success("Payment successful", { description: "Your plan is active. The GST invoice is under Invoices." });
          } catch (e) {
            toast.error("Payment received, confirmation pending", {
              description: e instanceof ApiError ? e.message : "Refresh in a minute; we confirm payments with Razorpay automatically.",
            });
          }
          setBusy(null);
          setParams((p) => (p.delete("plan"), p.delete("period"), p), { replace: true });
          refreshUsage();
          load();
          setTimeout(load, 4000); // the webhook adds the invoice a moment later
        },
      });
      rzp.on("payment.failed", (r) => {
        const d = (r as { error?: { description?: string } }).error?.description;
        toast.error("Payment failed", { description: d || "No money was taken. Try again or use another method." });
      });
      rzp.open();
    } catch (e) {
      toast.error("Couldn't start the payment", { description: e instanceof Error ? e.message : undefined });
      setBusy(null);
    }
  };

  const cancel = async () => {
    if (!b?.subscription) return;
    const until = day(b.subscription.current_end);
    if (!window.confirm(`Cancel your plan? It stays active until ${until}, then moves to Free. No further charges.`)) return;
    setBusy("cancel");
    try {
      await api("/api/billing/cancel", { method: "POST" });
      toast.success("Plan cancelled", { description: `You keep your plan until ${until}.` });
      load();
    } catch (e) {
      toast.error("Couldn't cancel", { description: e instanceof ApiError ? e.message : undefined });
    } finally {
      setBusy(null);
    }
  };

  const pct = usage && usage.allowance ? Math.min(100, Math.round(((usage.used + usage.reserved) / usage.allowance) * 100)) : 0;
  const sub = b?.subscription ?? null;
  const live = sub && ["active", "authenticated", "pending"].includes(sub.status);
  const wanted = params.get("plan");

  return (
    <section id="billing" className="scroll-mt-20 rounded-2xl border bg-surface p-5 shadow-md sm:p-6">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-heading text-h3 font-semibold">Billing</h3>
        {b?.test_mode && (
          <Badge variant="outline" className="border-warning/50 text-warning">
            Test mode: no real money
          </Badge>
        )}
      </div>

      {/* Current plan + usage */}
      <div className="mt-5">
        <p className="text-sm font-medium">
          {usage ? `${usage.plan_name} plan` : "Plan"}
          {usage?.unlimited && <span className="text-muted-foreground"> · unlimited (admin)</span>}
        </p>
        {sub && (live || sub.cancel_at_period_end || sub.status === "cancelled") && (
          <p className="mt-1 text-sm text-muted-foreground">
            {sub.cancel_at_period_end || sub.status === "cancelled" ? (
              <>
                Cancelled. Your {sub.plan} plan stays active until <span className="font-medium text-foreground">{day(sub.current_end)}</span>, then
                moves to Free.
              </>
            ) : sub.status === "active" ? (
              <>
                Billed {sub.period}. Renews on <span className="font-medium text-foreground">{day(sub.current_end)}</span>.
              </>
            ) : (
              <>Payment is being confirmed. This usually takes under a minute.</>
            )}
          </p>
        )}
        {!sub && usage?.plan_until && (
          <p className="mt-1 text-sm text-muted-foreground">
            Early access: free until{" "}
            <span className="font-medium text-foreground">{day(new Date(new Date(usage.plan_until).getTime() - 1).toISOString())}</span>, then your account
            moves to the Free plan automatically. Nothing is charged.
          </p>
        )}
        {usage && !usage.unlimited && usage.allowance !== null && (
          <div className="mt-3 max-w-sm">
            <div
              className="h-1.5 overflow-hidden rounded-full bg-surface-3"
              role="progressbar"
              aria-valuenow={pct}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label="Characters used this month"
            >
              <div className="h-full rounded-full bg-brand-gradient" style={{ width: `${pct}%` }} />
            </div>
            <p className="mt-1.5 font-mono text-xs text-muted-foreground tabular">
              {fmtChars(usage.used)} / {fmtChars(usage.allowance)} characters used · resets{" "}
              {new Date(usage.period_end).toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: "Asia/Kolkata" })}
            </p>
          </div>
        )}
      </div>

      {error && <p className="mt-4 text-sm text-danger">{error}</p>}

      {/* Plans */}
      {b && !b.enabled && (
        <p className="mt-5 text-sm text-muted-foreground">
          Online payments aren't open yet.{" "}
          <a href="https://aiwazz.in/pricing/" target="_blank" rel="noopener" className="font-medium text-foreground underline underline-offset-2">
            See plans
          </a>
        </p>
      )}
      {b?.enabled && !usage?.unlimited && (!live || sub?.status === "active") && !sub?.cancel_at_period_end && (
        <div className="mt-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm font-medium">{live ? "Change plan" : "Upgrade"}</p>
            <ToggleGroup type="single" variant="outline" size="sm" value={period} onValueChange={(v) => v && setPeriod(v as Period)} aria-label="Billing period">
              <ToggleGroupItem value="monthly" className="px-3">
                Monthly
              </ToggleGroupItem>
              <ToggleGroupItem value="yearly" className="px-3">
                Yearly −20%
              </ToggleGroupItem>
            </ToggleGroup>
          </div>
          <ul className="mt-3 grid gap-3 md:grid-cols-3">
            {b.plans.map((p) => {
              const current = live && sub ? sub.plan === p.id && sub.period === period : usage?.plan === p.id;
              const lower = ORDER.indexOf(p.id) < ORDER.indexOf((live && sub?.plan) || usage?.plan || "free");
              return (
                <li key={p.id} className={cn("flex flex-col rounded-xl border p-4", wanted === p.id && "border-primary ring-2 ring-primary/20")}>
                  <p className="text-sm font-semibold">{p.name}</p>
                  <p className="mt-2 font-heading text-2xl font-bold">
                    {inr(period === "monthly" ? p.monthly : p.yearly_per_month)}
                    <span className="ml-1 font-sans text-xs font-normal text-muted-foreground">/month</span>
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {period === "monthly"
                      ? `${inrPaise(p.total_monthly_paise)} per month incl. ${b.gst_rate}% GST`
                      : `${inrPaise(p.total_yearly_paise)} per year incl. ${b.gst_rate}% GST`}
                  </p>
                  <p className="mt-2 text-xs text-muted-foreground">{fmtChars(p.characters)} characters / month</p>
                  <Button
                    className="mt-4"
                    size="sm"
                    variant={wanted === p.id || p.id === "creator" ? "brand" : "outline"}
                    disabled={!!busy || current}
                    onClick={() => (live ? changePlan(p.id) : pay(p.id))}
                  >
                    {busy === p.id && <Loader2 className="animate-spin" />}
                    {current ? (
                      <>
                        <Check /> Current plan
                      </>
                    ) : sub?.pending_plan === p.id && sub?.pending_period === period ? (
                      "Starts at renewal"
                    ) : live && lower ? (
                      `Switch at renewal`
                    ) : lower ? (
                      `Switch to ${p.name}`
                    ) : (
                      `Upgrade to ${p.name}`
                    )}
                  </Button>
                </li>
              );
            })}
          </ul>
          {!live && (
            <div className="mt-3 flex max-w-xs items-center gap-2">
              <label htmlFor="coupon" className="shrink-0 text-xs text-muted-foreground">Coupon</label>
              <input id="coupon" value={coupon} onChange={(e) => setCoupon(e.target.value.toUpperCase())} placeholder="Optional"
                className="h-8 w-full rounded-lg border border-input bg-surface px-2 font-mono text-xs uppercase outline-none focus-visible:ring-2 focus-visible:ring-ring" />
            </div>
          )}
          <p className="mt-3 flex items-center gap-1.5 text-xs text-muted-foreground">
            <ShieldCheck className="size-3.5 shrink-0" aria-hidden="true" /> Paid securely through Razorpay (UPI, cards, net banking). Renews
            automatically; cancel any time.
          </p>
        </div>
      )}

      {/* Billing details */}
      {b && (
        <div className="mt-6 border-t pt-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-sm font-medium">Billing details</p>
              <p className="text-sm text-muted-foreground">
                {b.profile.name
                  ? `${b.profile.name} · ${b.states.find((s) => s.code === b.profile.state)?.name ?? ""}${b.profile.gstin ? ` · GSTIN ${b.profile.gstin}` : ""}`
                  : "Not added yet. Needed before your first payment."}
              </p>
            </div>
            {!editing && (
              <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
                {b.profile.name ? "Edit" : "Add details"}
              </Button>
            )}
          </div>
          {editing && (
            <div className="mt-4">
              <ProfileForm
                b={b}
                onCancel={() => (setEditing(false), setPending(null))}
                onSaved={(p) => {
                  setB({ ...b, profile: p });
                  setEditing(false);
                  if (pending) {
                    const id = pending;
                    setPending(null);
                    setTimeout(() => pay(id), 0);
                  }
                }}
              />
            </div>
          )}
        </div>
      )}

      {/* Invoices */}
      {b && b.invoices.length > 0 && (
        <div className="mt-6 border-t pt-5">
          <p className="text-sm font-medium">Invoices</p>
          <ul className="mt-2 divide-y">
            {b.invoices.map((i) => (
              <li key={i.id} className="flex items-center gap-3 py-2.5 text-sm">
                <FileText className="size-4 shrink-0 text-subtle-foreground" aria-hidden="true" />
                <span className="min-w-0 flex-1">
                  <span className="font-mono text-xs">{i.number}</span>
                  <span className="text-muted-foreground">
                    {" "}
                    · {day(i.issued_at)} · {i.plan} ({i.period})
                  </span>
                </span>
                <span className="font-mono text-xs tabular">{inrPaise(i.total_paise)}</span>
                <Button asChild variant="ghost" size="icon-sm" aria-label={`Download invoice ${i.number}`}>
                  <a href={`/api/billing/invoices/${i.id}/pdf`} download>
                    <Download />
                  </a>
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Cancel */}
      {live && sub && !sub.cancel_at_period_end && (
        <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t pt-5">
          <p className="max-w-md text-sm text-muted-foreground">Cancel any time. You keep your plan until the end of the period you paid for.</p>
          <Button variant="outline" size="sm" onClick={cancel} disabled={busy === "cancel"}>
            {busy === "cancel" && <Loader2 className="animate-spin" />} Cancel plan
          </Button>
        </div>
      )}
    </section>
  );
}
