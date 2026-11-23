import { AlertTriangle, Check, Copy, KeyRound, Loader2, Plus, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { AppShell } from "@/components/app-shell/app-shell";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import { timeAgo } from "@/lib/format";

type Key = { id: number; name: string; prefix: string; created_at: string; last_used_at: string | null; revoked: boolean };

function CopyButton({ value, label = "Copy" }: { value: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
          setDone(true);
          setTimeout(() => setDone(false), 1500);
        } catch {
          toast.error("Couldn't copy. Select the text and copy it manually.");
        }
      }}
    >
      {done ? <Check /> : <Copy />} {done ? "Copied" : label}
    </Button>
  );
}

const example = (key: string) => `curl -s -X POST 'https://login.aiwazz.in/api/tts?wait=true' \\
  -H 'X-API-Key: ${key}' \\
  -H 'Content-Type: application/json' \\
  -d '{"text":"नमस्ते दोस्तों!","voice":"hf_alpha","format":"mp3"}'
# → {"id": "...", "status": "done", "urls": {"mp3": "/api/audio/<id>?format=mp3", ...}}

curl -s -H 'X-API-Key: ${key}' -o voiceover.mp3 \\
  'https://login.aiwazz.in/api/audio/<id>?format=mp3'`;

export default function ApiKeysPage() {
  const [keys, setKeys] = useState<Key[] | null>(null);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<string | null>(null);
  const [revoke, setRevoke] = useState<Key | null>(null);
  const [revoking, setRevoking] = useState(false);

  const load = useCallback(() => {
    api<{ keys: Key[] }>("/api/keys").then(
      (r) => setKeys(r.keys),
      (e) => (setKeys([]), toast.error("Couldn't load API keys", { description: e instanceof ApiError ? e.message : undefined })),
    );
  }, []);
  useEffect(load, [load]);

  const create = async (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setCreating(true);
    try {
      const k = await api<Key & { key: string }>("/api/keys", { json: { name: name.trim() } });
      setCreated(k.key);
      setName("");
      load();
    } catch (err) {
      toast.error("Couldn't create the key", { description: err instanceof ApiError ? err.message : undefined });
    } finally {
      setCreating(false);
    }
  };

  const doRevoke = async () => {
    if (!revoke) return;
    setRevoking(true);
    try {
      await api(`/api/keys/${revoke.id}`, { method: "DELETE" });
      toast.success(`Revoked “${revoke.name}”`, { description: "Scripts using it stop working immediately." });
      setRevoke(null);
      load();
    } catch (err) {
      toast.error("Couldn't revoke the key", { description: err instanceof ApiError ? err.message : undefined });
    } finally {
      setRevoking(false);
    }
  };

  return (
    <AppShell title="API keys">
      <div className="mx-auto max-w-4xl space-y-6 p-3 sm:p-5 lg:p-6">
        <div>
          <h2 className="text-h2 font-semibold">API keys</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Generate voiceovers from scripts and video pipelines. Send the key in the <code className="font-mono text-xs">X-API-Key</code> header. Keys act as
            you, so keep them secret.
          </p>
        </div>

        <form onSubmit={create} className="flex flex-col gap-3 rounded-2xl border bg-surface p-4 shadow-md sm:flex-row sm:items-end">
          <div className="flex-1 space-y-2">
            <Label htmlFor="key-name">New key name</Label>
            <Input id="key-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={100} placeholder="e.g. Remotion pipeline" />
          </div>
          <Button type="submit" disabled={!name.trim() || creating}>
            {creating ? <Loader2 className="animate-spin" /> : <Plus />} Create key
          </Button>
        </form>

        <div className="rounded-2xl border bg-surface shadow-md">
          {keys === null ? (
            <div className="space-y-3 p-4" aria-busy="true">
              <Skeleton className="h-12" />
              <Skeleton className="h-12" />
            </div>
          ) : keys.length === 0 ? (
            <div className="flex flex-col items-center gap-2 px-6 py-12 text-center">
              <span className="grid size-11 place-items-center rounded-2xl border bg-surface-2 text-brand">
                <KeyRound className="size-5" aria-hidden="true" />
              </span>
              <p className="font-medium">No API keys yet</p>
              <p className="text-sm text-muted-foreground">Create one above to use AiWazz from your scripts.</p>
            </div>
          ) : (
            <ul className="divide-y">
              {keys.map((k) => (
                <li key={k.id} className="flex flex-wrap items-center gap-3 p-4">
                  <KeyRound className="size-4 text-muted-foreground" aria-hidden="true" />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">{k.name}</p>
                    <p className="text-xs text-muted-foreground">
                      <span className="font-mono">{k.prefix}…</span> · created {timeAgo(k.created_at)} ·{" "}
                      {k.last_used_at ? `last used ${timeAgo(k.last_used_at)}` : "never used"}
                    </p>
                  </div>
                  <Button variant="ghost" size="sm" onClick={() => setRevoke(k)} className="text-danger hover:text-danger">
                    <Trash2 /> Revoke
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <section aria-labelledby="usage" className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 id="usage" className="font-sans text-sm font-medium">
              Quick start
            </h3>
            <CopyButton value={example("YOUR_API_KEY")} label="Copy example" />
          </div>
          <pre className="overflow-x-auto rounded-2xl border bg-surface-2 p-4 font-mono text-xs leading-6">{example("YOUR_API_KEY")}</pre>
        </section>
      </div>

      {/* Shown once after creating a key */}
      <Dialog open={!!created} onOpenChange={(o) => !o && setCreated(null)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Your new API key</DialogTitle>
            <DialogDescription>Copy it now. For your security it won't be shown again.</DialogDescription>
          </DialogHeader>
          <div className="flex items-center gap-2 rounded-xl border bg-surface-2 p-3">
            <code className="min-w-0 flex-1 font-mono text-xs break-all">{created}</code>
            {created && <CopyButton value={created} />}
          </div>
          <p className="flex items-start gap-2 text-xs text-muted-foreground">
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-warning" aria-hidden="true" />
            Store it in your script's environment or secrets, never in code you share or commit.
          </p>
          <DialogFooter>
            <Button onClick={() => setCreated(null)}>Done</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!revoke} onOpenChange={(o) => !o && setRevoke(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Revoke “{revoke?.name}”?</DialogTitle>
            <DialogDescription>Any script using this key stops working immediately. This can't be undone.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRevoke(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={doRevoke} disabled={revoking}>
              {revoking ? <Loader2 className="animate-spin" /> : <Trash2 />} Revoke key
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </AppShell>
  );
}
