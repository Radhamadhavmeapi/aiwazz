import { Loader2, Play, Plus, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiAudio } from "@/lib/api";
import { VOICES } from "@/lib/voices";
import { ErrorState, LoadingRows, PageHeader, Section, Select } from "../components/page";
import { AdminShell } from "../components/shell";
import { adminApi, errMsg } from "../lib/admin-api";
import { useAdmin } from "../lib/admin-context";

type Entry = { id: number; word: string; say_as: string; updated_at: string };

export default function PronunciationsPage() {
  const { can } = useAdmin();
  const [items, setItems] = useState<Entry[] | null>(null);
  const [error, setError] = useState("");
  const [word, setWord] = useState("");
  const [sayAs, setSayAs] = useState("");
  const [voice, setVoice] = useState("hf_alpha");
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const load = useCallback(() => {
    adminApi<{ items: Entry[] }>("/api/admin/pronunciations").then((r) => setItems(r.items), (e) => setError(errMsg(e)));
  }, []);
  useEffect(load, [load]);
  const play = async (text: string, key: string) => {
    setBusy(key);
    try {
      const blob = await apiAudio("/api/pronunciations/test", { say_as: text, voice });
      const url = URL.createObjectURL(blob);
      const a = new Audio(url);
      a.onended = () => URL.revokeObjectURL(url);
      await a.play();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(null); }
  };
  const save = async (e: FormEvent) => {
    e.preventDefault();
    try { await adminApi("/api/admin/pronunciations", { json: { word, say_as: sayAs } }); setWord(""); setSayAs(""); load(); toast.success("Saved"); } catch (err) { toast.error(errMsg(err)); }
  };
  const write = can("pronunciations.write");
  const shown = (items ?? []).filter((i) => !q || i.word.toLowerCase().includes(q.toLowerCase()) || i.say_as.includes(q));
  return (
    <AdminShell title="Pronunciations">
      <PageHeader title="Global pronunciations" description="Applies to every user after their own list and inline fixes (priority: inline → request → user list → this list). Whole word, any case." />
      {write && (
        <Section title="Add or update" className="mb-4">
          <form onSubmit={save} className="grid gap-2 sm:grid-cols-[1fr_1fr_auto_auto]">
            <Input aria-label="Word" value={word} onChange={(e) => setWord(e.target.value)} placeholder="Word, e.g. GST" maxLength={64} />
            <Input aria-label="Say as" value={sayAs} onChange={(e) => setSayAs(e.target.value)} placeholder="Say as, e.g. जी एस टी" maxLength={128} />
            <Button type="button" variant="outline" disabled={!sayAs.trim() || busy === "new"} onClick={() => play(sayAs, "new")}>{busy === "new" ? <Loader2 className="animate-spin" /> : <Play />} Test</Button>
            <Button type="submit" disabled={!word.trim() || !sayAs.trim()}><Plus /> Save</Button>
          </form>
        </Section>
      )}
      <Section title={`Entries (${items?.length ?? 0})`} actions={
        <div className="flex gap-2"><Select aria-label="Test voice" value={voice} onChange={(e) => setVoice(e.target.value)}>{VOICES.map((v) => <option key={v.id} value={v.id}>{v.name} ({v.lang === "h" ? "HI" : v.lang === "a" ? "US" : "UK"})</option>)}</Select>
          <Input aria-label="Filter" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter…" className="h-9 w-40" /></div>}>
        {error ? <ErrorState message={error} onRetry={load} /> : !items ? <LoadingRows rows={4} /> : !shown.length ? <p className="py-6 text-center text-sm text-muted-foreground">No entries.</p> : (
          <ul className="divide-y">
            {shown.map((i) => (
              <li key={i.id} className="flex items-center gap-3 py-2 text-sm">
                <span className="w-40 shrink-0 truncate font-medium">{i.word}</span>
                <span className="min-w-0 flex-1 truncate text-muted-foreground">→ {i.say_as}</span>
                <Button size="icon-xs" variant="ghost" aria-label={`Play ${i.word}`} disabled={busy === String(i.id)} onClick={() => play(i.say_as, String(i.id))}>{busy === String(i.id) ? <Loader2 className="animate-spin" /> : <Play />}</Button>
                {write && <Button size="icon-xs" variant="ghost" aria-label={`Delete ${i.word}`} onClick={async () => {
                  try { await adminApi(`/api/admin/pronunciations/${i.id}`, { method: "DELETE" }); load(); } catch (e) { toast.error(errMsg(e)); }
                }}><Trash2 /></Button>}
              </li>
            ))}
          </ul>
        )}
      </Section>
    </AdminShell>
  );
}
