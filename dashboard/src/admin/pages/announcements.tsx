import type { ColumnDef } from "@tanstack/react-table";
import { ExternalLink, Plus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { DataTable } from "../components/data-table";
import { FormDialog } from "../components/form-dialog";
import { Field, fmtDate, PageHeader, Pill, Select } from "../components/page";
import { AdminShell } from "../components/shell";
import { adminApi } from "../lib/admin-api";
import { useAdmin } from "../lib/admin-context";

type Ann = { id: number; text: string; level: string; audience: string; starts_at: string | null; ends_at: string | null; dismissible: boolean; active: boolean; state: string };
type Cl = { id: number; title: string; body_md: string; tag: string; is_published: boolean; published_on: string };
const AUD: Record<string, string> = { all: "Everyone", free: "Free plan", paid: "Paid plans", admins: "Staff only", "plan:starter": "Starter", "plan:creator": "Creator", "plan:pro": "Pro" };
const toLocal = (iso: string | null) => (iso ? new Date(iso).toISOString().slice(0, 16) : "");
const fromLocal = (v: string) => (v ? new Date(v).toISOString() : null);
const blankAnn = { text: "", level: "info", audience: "all", starts_at: "", ends_at: "", dismissible: true, active: true };
const today = () => new Date(Date.now() + 5.5 * 3600_000).toISOString().slice(0, 10);

function Banners() {
  const { can } = useAdmin();
  const [form, setForm] = useState<{ id: number | null; f: typeof blankAnn } | null>(null);
  const [reload, setReload] = useState(0);
  const cols: ColumnDef<Ann, unknown>[] = [
    { id: "text", header: "Banner", cell: ({ row: { original: a } }) => <div className="max-w-md"><p className="text-sm">{a.text}</p><p className="text-xs text-muted-foreground">{AUD[a.audience]} · {a.level}{a.dismissible ? " · dismissible" : ""}</p></div> },
    { id: "when", header: "Shown", cell: ({ row: { original: a } }) => <span className="text-xs">{a.starts_at ? fmtDate(a.starts_at) : "now"} → {a.ends_at ? fmtDate(a.ends_at) : "until switched off"}</span> },
    { id: "state", header: "State", cell: ({ row }) => <Pill tone={row.original.state === "live" ? "green" : row.original.state === "scheduled" ? "blue" : "gray"}>{row.original.state}</Pill> },
  ];
  return (
    <>
      <DataTable<Ann> id="announcements" endpoint="/api/admin/announcements" columns={cols} reloadKey={reload} searchPlaceholder={null} emptyTitle="No banners yet"
        onRowClick={can("announcements.write") ? (a) => setForm({ id: a.id, f: { ...a, starts_at: toLocal(a.starts_at), ends_at: toLocal(a.ends_at) } }) : undefined}
        toolbar={can("announcements.write") && <Button size="sm" variant="brand" onClick={() => setForm({ id: null, f: { ...blankAnn } })}><Plus /> New banner</Button>} />
      <FormDialog open={!!form} onOpenChange={(o) => !o && setForm(null)} title={form?.id ? "Edit banner" : "New banner"} disabled={(form?.f.text.trim().length ?? 0) < 3}
        onSubmit={async () => {
          const body = { ...form!.f, starts_at: fromLocal(form!.f.starts_at), ends_at: fromLocal(form!.f.ends_at) };
          await adminApi(form!.id ? `/api/admin/announcements/${form!.id}` : "/api/admin/announcements", { method: form!.id ? "PUT" : "POST", json: body });
          toast.success("Saved");
          setReload((n) => n + 1);
        }}>
        {form && (
          <>
            <Field label="Text (shown at the top of the app)" htmlFor="an-text"><Textarea id="an-text" rows={3} maxLength={300} value={form.f.text} onChange={(e) => setForm({ ...form, f: { ...form.f, text: e.target.value } })} /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Type"><Select className="w-full" value={form.f.level} onChange={(e) => setForm({ ...form, f: { ...form.f, level: e.target.value } })}><option value="info">Info</option><option value="warning">Warning</option></Select></Field>
              <Field label="Audience"><Select className="w-full" value={form.f.audience} onChange={(e) => setForm({ ...form, f: { ...form.f, audience: e.target.value } })}>{Object.entries(AUD).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
              <Field label="Start (your time; empty = now)" htmlFor="an-start"><Input id="an-start" type="datetime-local" value={form.f.starts_at} onChange={(e) => setForm({ ...form, f: { ...form.f, starts_at: e.target.value } })} /></Field>
              <Field label="End (empty = until switched off)" htmlFor="an-end"><Input id="an-end" type="datetime-local" value={form.f.ends_at} onChange={(e) => setForm({ ...form, f: { ...form.f, ends_at: e.target.value } })} /></Field>
            </div>
            <label className="flex items-center gap-2 text-sm"><Switch checked={form.f.dismissible} onCheckedChange={(v) => setForm({ ...form, f: { ...form.f, dismissible: v } })} aria-label="Dismissible" /> Users can dismiss it</label>
            <label className="flex items-center gap-2 text-sm"><Switch checked={form.f.active} onCheckedChange={(v) => setForm({ ...form, f: { ...form.f, active: v } })} aria-label="Active" /> Active</label>
          </>
        )}
      </FormDialog>
    </>
  );
}

function Changelog() {
  const { can } = useAdmin();
  const [form, setForm] = useState<{ id: number | null; f: Omit<Cl, "id"> } | null>(null);
  const [reload, setReload] = useState(0);
  const cols: ColumnDef<Cl, unknown>[] = [
    { id: "published_on", header: "Date", meta: { sortKey: "published_on" }, cell: ({ row }) => <span className="text-xs whitespace-nowrap">{row.original.published_on}</span> },
    { id: "title", header: "Title", cell: ({ row: { original: c } }) => <div><p className="font-medium">{c.title}</p><p className="line-clamp-1 text-xs text-muted-foreground">{c.body_md}</p></div> },
    { id: "tag", header: "Tag", cell: ({ row }) => <Pill tone={row.original.tag === "new" ? "green" : row.original.tag === "fixed" ? "amber" : "blue"}>{row.original.tag}</Pill> },
    { id: "pub", header: "Public", cell: ({ row }) => <Pill tone={row.original.is_published ? "green" : "gray"}>{row.original.is_published ? "published" : "draft"}</Pill> },
  ];
  return (
    <>
      <DataTable<Cl> id="changelog" endpoint="/api/admin/changelog" columns={cols} reloadKey={reload} searchPlaceholder={null} emptyTitle="No changelog entries yet"
        onRowClick={can("announcements.write") ? (c) => setForm({ id: c.id, f: { ...c } }) : undefined}
        toolbar={<>
          <Button size="sm" variant="outline" asChild><a href="https://aiwazz.in/changelog/" target="_blank" rel="noopener"><ExternalLink /> View page</a></Button>
          {can("announcements.write") && <Button size="sm" variant="brand" onClick={() => setForm({ id: null, f: { title: "", body_md: "", tag: "new", is_published: false, published_on: today() } })}><Plus /> New entry</Button>}
        </>} />
      <FormDialog open={!!form} onOpenChange={(o) => !o && setForm(null)} title={form?.id ? "Edit entry" : "New changelog entry"} wide
        description="Publishing (or changing a published entry) rebuilds aiwazz.in/changelog/ in the background (a few minutes)."
        disabled={(form?.f.title.trim().length ?? 0) < 3 || !form?.f.body_md.trim()}
        onSubmit={async () => {
          const r = await adminApi<{ landing_rebuild?: string }>(form!.id ? `/api/admin/changelog/${form!.id}` : "/api/admin/changelog", { method: form!.id ? "PUT" : "POST", json: form!.f });
          toast.success(r.landing_rebuild ? `Saved; landing rebuild ${r.landing_rebuild}` : "Saved");
          setReload((n) => n + 1);
        }}>
        {form && (
          <>
            <Field label="Title" htmlFor="cl-title"><Input id="cl-title" value={form.f.title} onChange={(e) => setForm({ ...form, f: { ...form.f, title: e.target.value } })} /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Date" htmlFor="cl-date"><Input id="cl-date" type="date" value={form.f.published_on} onChange={(e) => setForm({ ...form, f: { ...form.f, published_on: e.target.value } })} /></Field>
              <Field label="Tag"><Select className="w-full" value={form.f.tag} onChange={(e) => setForm({ ...form, f: { ...form.f, tag: e.target.value } })}><option value="new">New</option><option value="improved">Improved</option><option value="fixed">Fixed</option></Select></Field>
            </div>
            <Field label="Text (Markdown)" htmlFor="cl-body"><Textarea id="cl-body" rows={8} className="font-mono text-xs" value={form.f.body_md} onChange={(e) => setForm({ ...form, f: { ...form.f, body_md: e.target.value } })} /></Field>
            <label className="flex items-center gap-2 text-sm"><Switch checked={form.f.is_published} onCheckedChange={(v) => setForm({ ...form, f: { ...form.f, is_published: v } })} aria-label="Published" /> Published on aiwazz.in/changelog/</label>
          </>
        )}
      </FormDialog>
    </>
  );
}

export default function AnnouncementsPage() {
  return (
    <AdminShell title="Announcements">
      <PageHeader title="Announcements & changelog" description="In-app banners (by audience, scheduled) and the public changelog." />
      <Tabs defaultValue="banners">
        <TabsList className="mb-4"><TabsTrigger value="banners">In-app banners</TabsTrigger><TabsTrigger value="changelog">Changelog</TabsTrigger></TabsList>
        <TabsContent value="banners"><Banners /></TabsContent>
        <TabsContent value="changelog"><Changelog /></TabsContent>
      </Tabs>
    </AdminShell>
  );
}
