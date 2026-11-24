import { ExternalLink, Loader2, Pause, Pencil, Play, RefreshCw, Sparkles } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { FormDialog } from "../components/form-dialog";
import { ErrorState, Field, LoadingRows, PageHeader, Pill, Section, Select } from "../components/page";
import { AdminShell } from "../components/shell";
import { adminApi, errMsg } from "../lib/admin-api";
import { useAdmin } from "../lib/admin-context";
import { planName } from "../lib/plans";

type V = {
  id: string; name: string; lang: string; lang_name?: string; gender: string; tone: string; tags: string[]; enabled: boolean; display_name: string;
  sort_order: number; is_new: boolean; min_plan: string; uses_30d: number; sample_url?: string;
};
type Studio = V & { is_public: boolean; consent: { status: string; source_type: string; speaker: string } | null; preview_url?: string };
type St = { id: string; name: string; description: string; speed: number; loudness_lufs: number; enabled: boolean; sort_order: number };
type Data = { voices: V[]; studio: Studio[]; styles: St[]; previews: { name: string; url: string; available: boolean }[]; sample_job_running: boolean };

function usePlayer() {
  const ref = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);
  const toggle = (id: string, url: string) => {
    if (playing === id) return (ref.current?.pause(), setPlaying(null));
    ref.current?.pause();
    const a = new Audio(`${url}?t=${Date.now()}`);
    ref.current = a;
    a.onended = () => setPlaying(null);
    void a.play().then(() => setPlaying(id), () => toast.error("Couldn't play the sample"));
  };
  return { playing, toggle };
}

export default function VoicesPage() {
  const { can, me } = useAdmin();
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState("");
  const [edit, setEdit] = useState<V | null>(null);
  const [form, setForm] = useState({ enabled: true, display_name: "", description: "", tags: "", sort_order: 0, is_new: false, min_plan: "free" });
  const [styleEdit, setStyleEdit] = useState<St | null>(null);
  const [sform, setSform] = useState({ enabled: true, display_name: "", description: "", sort_order: 0 });
  const [busy, setBusy] = useState<string | null>(null);
  const [publish, setPublish] = useState<Studio | null>(null);
  const [reason, setReason] = useState("");
  const { playing, toggle } = usePlayer();
  const load = useCallback(() => {
    adminApi<Data>("/api/admin/voices").then(setData, (e) => setError(errMsg(e)));
  }, []);
  useEffect(load, [load]);
  const write = can("voices.write");
  if (error) return <AdminShell title="Voices & styles"><ErrorState message={error} onRetry={load} /></AdminShell>;
  if (!data) return <AdminShell title="Voices & styles"><LoadingRows rows={8} /></AdminShell>;
  const openEdit = (v: V) => {
    setForm({ enabled: v.enabled, display_name: v.display_name === v.id ? "" : v.name, description: v.tone, tags: v.tags.join(", "), sort_order: v.sort_order, is_new: v.is_new, min_plan: v.min_plan });
    setEdit(v);
  };
  return (
    <AdminShell title="Voices & styles">
      <PageHeader title="Voices & styles" description="Switch voices and styles on or off, rename them, set the order, a “new” badge and the plan a voice needs. Changes show in the app within 30 seconds." />
      <Section title="Voices" description="Built-in Kokoro voices. ▶ plays the current sample; regenerate makes a new one with today's engine (published to both sites and committed).">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead><tr className="border-b text-left text-xs text-muted-foreground"><th className="py-2">Voice</th><th>Tags</th><th>Plan</th><th>Uses (30d)</th><th>Status</th><th /></tr></thead>
            <tbody>
              {data.voices.map((v) => (
                <tr key={v.id} className="border-b last:border-0">
                  <td className="py-2.5">
                    <div className="flex items-center gap-2">
                      <Button size="icon-xs" variant="outline" aria-label={playing === v.id ? `Stop ${v.name}` : `Play ${v.name}`} onClick={() => toggle(v.id, v.sample_url!)}>{playing === v.id ? <Pause /> : <Play />}</Button>
                      <div><p className="font-medium">{v.name} {v.is_new && <Pill tone="green">new</Pill>}</p><p className="text-xs text-muted-foreground"><span className="font-mono">{v.id}</span> · {v.tone}</p></div>
                    </div>
                  </td>
                  <td><div className="flex flex-wrap gap-1">{v.tags.map((t) => <Pill key={t}>{t}</Pill>)}</div></td>
                  <td className="text-xs">{planName(v.min_plan)}+</td>
                  <td className="tabular">{v.uses_30d}</td>
                  <td><Pill tone={v.enabled ? "green" : "gray"}>{v.enabled ? "on" : "off"}</Pill></td>
                  <td className="text-right whitespace-nowrap">
                    {write && <>
                      <Button size="icon-xs" variant="ghost" aria-label={`Edit ${v.name}`} onClick={() => openEdit(v)}><Pencil /></Button>
                      <Button size="xs" variant="ghost" disabled={busy === v.id} onClick={async () => {
                        setBusy(v.id);
                        try { await adminApi(`/api/admin/voices/${v.id}/sample`, { method: "POST" }); toast.success(`New sample for ${v.name}`); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(null); }
                      }}>{busy === v.id ? <Loader2 className="animate-spin" /> : <RefreshCw />} Sample</Button>
                    </>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Section title="Studio voices" description="Custom (clone) voices. Private (owner-only) until the owner promotes one; promoting needs an active consent record.">
          {!data.studio.length ? <p className="text-sm text-muted-foreground">No studio voices loaded (voice-clone worker off?).</p> : (
            <ul className="divide-y">
              {data.studio.map((v) => (
                <li key={v.id} className="flex flex-wrap items-center gap-2 py-2.5 text-sm">
                  {v.preview_url && <Button size="icon-xs" variant="outline" aria-label={`Play ${v.name}`} onClick={() => toggle(v.id, v.preview_url!)}>{playing === v.id ? <Pause /> : <Play />}</Button>}
                  <div className="min-w-0 flex-1"><p className="font-medium">{v.name}</p><p className="text-xs text-muted-foreground"><span className="font-mono">{v.id}</span> · consent {v.consent ? `${v.consent.status} (${v.consent.source_type})` : "missing"}</p></div>
                  <Pill tone={v.is_public ? "green" : "gray"}>{v.is_public ? "public" : "owner-only"}</Pill>
                  {me?.user.role === "owner" && <Button size="xs" variant="outline" onClick={() => (setReason(""), setPublish(v))}><Sparkles /> {v.is_public ? "Make private" : "Promote"}</Button>}
                </li>
              ))}
            </ul>
          )}
        </Section>
        <Section title="Voice Lab & custom-voice samples" description="Research pages (owner listening). Open only while the admin panel is unlocked.">
          <ul className="space-y-2 text-sm">
            {data.previews.map((p) => (
              <li key={p.name} className="flex items-center justify-between gap-2">
                <span className="font-medium capitalize">{p.name.replace("-", " ")}</span>
                {p.available ? <Button size="xs" variant="outline" asChild><a href={p.url} target="_blank" rel="noopener"><ExternalLink /> Open</a></Button> : <span className="text-xs text-muted-foreground">no files on the server</span>}
              </li>
            ))}
          </ul>
        </Section>
      </div>

      <Section title="Styles" className="mt-4" description="Speaking styles (pace, pauses, loudness). Never called emotions.">
        <ul className="divide-y">
          {data.styles.map((s) => (
            <li key={s.id} className="flex flex-wrap items-center gap-3 py-2.5 text-sm">
              <div className="min-w-0 flex-1"><p className="font-medium">{s.name}</p><p className="text-xs text-muted-foreground">{s.description} · {s.speed}× · {s.loudness_lufs} LUFS</p></div>
              <Pill tone={s.enabled ? "green" : "gray"}>{s.enabled ? "on" : "off"}</Pill>
              {write && <Button size="icon-xs" variant="ghost" aria-label={`Edit ${s.name}`} onClick={() => (setSform({ enabled: s.enabled, display_name: s.name, description: s.description, sort_order: s.sort_order }), setStyleEdit(s))}><Pencil /></Button>}
            </li>
          ))}
        </ul>
      </Section>

      <FormDialog open={!!edit} onOpenChange={(o) => !o && setEdit(null)} title={`Edit ${edit?.id}`}
        onSubmit={async () => {
          await adminApi(`/api/admin/voices/${edit!.id}`, { method: "PUT", json: { ...form, tags: form.tags.split(",").map((t) => t.trim()).filter(Boolean) } });
          toast.success("Saved");
          load();
        }}>
        <label className="flex items-center gap-2 text-sm"><Switch checked={form.enabled} onCheckedChange={(v) => setForm({ ...form, enabled: v })} aria-label="Enabled" /> Available in the app</label>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Display name" htmlFor="v-name"><Input id="v-name" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} /></Field>
          <Field label="Order" htmlFor="v-order"><Input id="v-order" type="number" min={0} value={form.sort_order} onChange={(e) => setForm({ ...form, sort_order: Number(e.target.value) })} /></Field>
        </div>
        <Field label="Description (voice card)" htmlFor="v-desc"><Input id="v-desc" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
        <Field label="Tags (comma separated)" htmlFor="v-tags" hint="e.g. female, Hindi, warm"><Input id="v-tags" value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Plan needed"><Select className="w-full" value={form.min_plan} onChange={(e) => setForm({ ...form, min_plan: e.target.value })}>
            {["free", "starter", "creator", "pro"].map((p) => <option key={p} value={p}>{planName(p)} and up</option>)}</Select></Field>
          <label className="flex items-end gap-2 pb-2 text-sm"><Switch checked={form.is_new} onCheckedChange={(v) => setForm({ ...form, is_new: v })} aria-label="New badge" /> “New” badge</label>
        </div>
      </FormDialog>
      <FormDialog open={!!styleEdit} onOpenChange={(o) => !o && setStyleEdit(null)} title={`Edit ${styleEdit?.id}`}
        onSubmit={async () => { await adminApi(`/api/admin/styles/${styleEdit!.id}`, { method: "PUT", json: sform }); toast.success("Saved"); load(); }}>
        <label className="flex items-center gap-2 text-sm"><Switch checked={sform.enabled} onCheckedChange={(v) => setSform({ ...sform, enabled: v })} aria-label="Enabled" /> Available in the app</label>
        <Field label="Name" htmlFor="s-name"><Input id="s-name" value={sform.display_name} onChange={(e) => setSform({ ...sform, display_name: e.target.value })} /></Field>
        <Field label="Description" htmlFor="s-desc"><Input id="s-desc" value={sform.description} onChange={(e) => setSform({ ...sform, description: e.target.value })} /></Field>
        <Field label="Order" htmlFor="s-order"><Input id="s-order" type="number" min={0} value={sform.sort_order} onChange={(e) => setSform({ ...sform, sort_order: Number(e.target.value) })} /></Field>
      </FormDialog>
      <FormDialog open={!!publish} onOpenChange={(o) => !o && setPublish(null)} title={publish?.is_public ? `Make ${publish?.name} owner-only` : `Promote ${publish?.name} to all users`}
        description={publish?.is_public ? "Only you will see this voice again." : "Every user will see and can use this studio voice. Remember the Learn guide and pricing note (CLAUDE.md). Asks you to confirm it's you."}
        disabled={reason.trim().length < 3} submitLabel={publish?.is_public ? "Make private" : "Promote"}
        onSubmit={async () => { await adminApi(`/api/admin/voices/${publish!.id}/publish`, { json: { public: !publish!.is_public, reason } }); toast.success("Updated"); load(); }}>
        <Field label="Reason (audit log)" htmlFor="pub-reason"><Input id="pub-reason" value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
      </FormDialog>
    </AdminShell>
  );
}
