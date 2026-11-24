import {
  Globe,
  Loader2,
  Pencil,
  Play,
  Plus,
  Square,
  Trash2,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { api, apiAudio, ApiError } from "@/lib/api";
import { VOICES } from "@/lib/voices";

type Entry = { id: number; word: string; say_as: string };
type Lists = {
  items: Entry[];
  global: Entry[];
  builtin: { word: string; say_as: string; note: string }[];
  can_edit_global: boolean;
  max: number;
};

const errMsg = (e: unknown) =>
  e instanceof ApiError ? e.message : "Something went wrong. Please try again.";

/** ▶ plays how `say_as` sounds in the chosen voice (POST /api/pronunciations/test; not counted, not saved). */
function useTester() {
  const audio = useRef<HTMLAudioElement | null>(null);
  const [state, setState] = useState<{ key: string; loading: boolean } | null>(
    null,
  );
  const stop = useCallback(() => {
    audio.current?.pause();
    setState(null);
  }, []);
  useEffect(() => () => audio.current?.pause(), []);
  const play = async (key: string, sayAs: string, voice: string) => {
    if (state?.key === key) return stop();
    audio.current?.pause();
    setState({ key, loading: true });
    try {
      const blob = await apiAudio("/api/pronunciations/test", {
        say_as: sayAs,
        voice,
      });
      const a = new Audio(URL.createObjectURL(blob));
      audio.current = a;
      a.onended = () => setState(null);
      setState({ key, loading: false });
      await a.play();
    } catch (e) {
      setState(null);
      toast.error("Couldn't play the test", { description: errMsg(e) });
    }
  };
  return { state, play };
}

function TestButton({
  id,
  sayAs,
  voice,
  tester,
}: {
  id: string;
  sayAs: string;
  voice: string;
  tester: ReturnType<typeof useTester>;
}) {
  const on = tester.state?.key === id;
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon-sm"
      disabled={!sayAs.trim()}
      onClick={() => void tester.play(id, sayAs, voice)}
      aria-label={on ? "Stop" : `Test how “${sayAs}” sounds`}
    >
      {on && tester.state?.loading ? (
        <Loader2 className="animate-spin" />
      ) : on ? (
        <Square className="fill-current" />
      ) : (
        <Play className="fill-current" />
      )}
    </Button>
  );
}

function EntryForm({
  initial,
  onSave,
  onCancel,
  voice,
  tester,
  idPrefix,
}: {
  initial?: Entry;
  onSave: (word: string, sayAs: string) => Promise<void>;
  onCancel?: () => void;
  voice: string;
  tester: ReturnType<typeof useTester>;
  idPrefix: string;
}) {
  const [word, setWord] = useState(initial?.word ?? "");
  const [sayAs, setSayAs] = useState(initial?.say_as ?? "");
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await onSave(word, sayAs);
      if (!initial) (setWord(""), setSayAs(""));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form
      onSubmit={submit}
      className="grid gap-3 sm:grid-cols-[1fr_1.4fr_auto] sm:items-end"
    >
      <div className="space-y-1.5">
        <Label
          htmlFor={`${idPrefix}-word`}
          className="text-xs text-muted-foreground"
        >
          Word
        </Label>
        <Input
          id={`${idPrefix}-word`}
          value={word}
          onChange={(e) => setWord(e.target.value)}
          placeholder="e.g. Kalyan"
          maxLength={64}
          required
        />
      </div>
      <div className="space-y-1.5">
        <Label
          htmlFor={`${idPrefix}-say`}
          className="text-xs text-muted-foreground"
        >
          Say it as
        </Label>
        <div className="flex gap-1">
          <Input
            id={`${idPrefix}-say`}
            value={sayAs}
            onChange={(e) => setSayAs(e.target.value)}
            placeholder="e.g. कल्याण"
            maxLength={128}
            required
          />
          <TestButton
            id={`${idPrefix}-form`}
            sayAs={sayAs}
            voice={voice}
            tester={tester}
          />
        </div>
      </div>
      <div className="flex gap-2">
        <Button type="submit" disabled={busy || !word.trim() || !sayAs.trim()}>
          {busy ? (
            <Loader2 className="animate-spin" />
          ) : initial ? null : (
            <Plus />
          )}{" "}
          {initial ? "Save" : "Add"}
        </Button>
        {onCancel && (
          <Button type="button" variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        )}
      </div>
    </form>
  );
}

function EntryList({
  entries,
  editable,
  scope,
  voice,
  tester,
  onSave,
  onDelete,
}: {
  entries: Entry[];
  editable: boolean;
  scope: string;
  voice: string;
  tester: ReturnType<typeof useTester>;
  onSave: (word: string, sayAs: string) => Promise<void>;
  onDelete: (e: Entry) => Promise<void>;
}) {
  const [editing, setEditing] = useState<number | null>(null);
  return (
    <ul className="divide-y rounded-xl border">
      {entries.map((e) =>
        editing === e.id ? (
          <li key={e.id} className="p-3">
            <EntryForm
              initial={e}
              voice={voice}
              tester={tester}
              idPrefix={`${scope}-${e.id}`}
              onSave={async (w, s) => {
                await onSave(w, s); // save first, so a failed save never loses the old entry
                if (w.trim().toLowerCase() !== e.word.toLowerCase())
                  await onDelete(e);
                setEditing(null);
              }}
              onCancel={() => setEditing(null)}
            />
          </li>
        ) : (
          <li key={e.id} className="flex items-center gap-3 px-3 py-2">
            <div className="min-w-0 flex-1 text-sm">
              <span className="font-medium">{e.word}</span>
              <span className="mx-2 text-subtle-foreground" aria-hidden="true">
                →
              </span>
              <span className="sr-only"> is said as </span>
              <span className="text-muted-foreground">{e.say_as}</span>
            </div>
            <TestButton
              id={`${scope}-${e.id}`}
              sayAs={e.say_as}
              voice={voice}
              tester={tester}
            />
            {editable && (
              <>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => setEditing(e.id)}
                  aria-label={`Edit ${e.word}`}
                >
                  <Pencil />
                </Button>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => void onDelete(e)}
                  aria-label={`Remove ${e.word}`}
                >
                  <Trash2 />
                </Button>
              </>
            )}
          </li>
        ),
      )}
    </ul>
  );
}

export function PronunciationsCard() {
  const [lists, setLists] = useState<Lists | null>(null);
  const [voice, setVoice] = useState("hf_alpha");
  const tester = useTester();
  const load = useCallback(
    () =>
      api<Lists>("/api/pronunciations").then(setLists, (e) =>
        toast.error("Couldn't load pronunciations", { description: errMsg(e) }),
      ),
    [],
  );
  useEffect(() => void load(), [load]);
  useEffect(() => {
    if (location.hash === "#pronunciations")
      document.getElementById("pronunciations")?.scrollIntoView();
  }, []);

  const save = (global: boolean) => async (word: string, sayAs: string) => {
    try {
      await api(global ? "/api/admin/pronunciations" : "/api/pronunciations", {
        json: { word, say_as: sayAs },
      });
      toast.success(`Saved: ${word.trim()} → ${sayAs.trim()}`);
      await load();
    } catch (e) {
      toast.error("Couldn't save", { description: errMsg(e) });
      throw e;
    }
  };
  const remove = (global: boolean) => async (e: Entry) => {
    try {
      await api(
        `${global ? "/api/admin/pronunciations" : "/api/pronunciations"}/${e.id}`,
        { method: "DELETE" },
      );
      await load();
    } catch (err) {
      toast.error("Couldn't remove", { description: errMsg(err) });
    }
  };

  return (
    <section
      id="pronunciations"
      className="scroll-mt-20 rounded-2xl border bg-surface p-5 shadow-md sm:p-6"
    >
      <h3 className="font-heading text-h3 font-semibold">Pronunciations</h3>
      <p className="mt-1 text-sm text-muted-foreground">
        Teach the voice how to say names, brands and short forms. Matches whole
        words, any capitalisation, in every voiceover and API call. For one
        script only, write{" "}
        <code className="rounded bg-surface-2 px-1 font-mono text-xs">
          [word](say it as)
        </code>{" "}
        in the script.{" "}
        <a
          href="https://aiwazz.in/learn/fix-pronunciation/"
          target="_blank"
          rel="noopener"
          className="text-brand underline-offset-2 hover:underline"
        >
          How to write a pronunciation
        </a>
      </p>

      <div className="mt-5 flex flex-wrap items-center gap-2 text-sm">
        <Label htmlFor="pron-voice" className="text-xs text-muted-foreground">
          ▶ test with
        </Label>
        <select
          id="pron-voice"
          value={voice}
          onChange={(e) => setVoice(e.target.value)}
          className="h-8 rounded-lg border border-input bg-surface px-2 text-sm"
        >
          {VOICES.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name} (
              {v.lang === "h" ? "Hindi" : v.lang === "a" ? "US" : "UK"})
            </option>
          ))}
        </select>
        <span className="text-xs text-subtle-foreground">
          Tests don’t use your characters.
        </span>
      </div>

      <div className="mt-4 space-y-3">
        <EntryForm
          voice={voice}
          tester={tester}
          idPrefix="pron-new"
          onSave={save(false)}
        />
        {lists === null ? (
          <Skeleton className="h-24 rounded-xl" />
        ) : lists.items.length ? (
          <EntryList
            entries={lists.items}
            editable
            scope="mine"
            voice={voice}
            tester={tester}
            onSave={save(false)}
            onDelete={remove(false)}
          />
        ) : (
          <p className="rounded-xl border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">
            No words yet. Add a name the voice gets wrong, then press ▶ to hear
            the fix.
          </p>
        )}
        {lists && lists.items.length > 0 && (
          <p className="text-xs text-subtle-foreground">
            {lists.items.length} of {lists.max} words
          </p>
        )}
      </div>

      {lists && (
        <div className="mt-6 border-t pt-5">
          <h4 className="flex items-center gap-2 text-sm font-semibold">
            <Globe className="size-4 text-brand" aria-hidden="true" /> Built in
            for everyone
          </h4>
          <p className="mt-1 text-xs text-muted-foreground">
            Your own list wins when the same word is in both.
          </p>
          <div className="mt-3 space-y-3">
            {lists.can_edit_global && (
              <EntryForm
                voice={voice}
                tester={tester}
                idPrefix="pron-global"
                onSave={save(true)}
              />
            )}
            <EntryList
              entries={lists.global}
              editable={lists.can_edit_global}
              scope="global"
              voice={voice}
              tester={tester}
              onSave={save(true)}
              onDelete={remove(true)}
            />
            <ul className="space-y-1 text-xs text-muted-foreground">
              {lists.builtin.map((b) => (
                <li key={b.word}>
                  <span className="font-medium text-foreground">{b.word}</span>{" "}
                  → {b.say_as}. {b.note}.
                </li>
              ))}
            </ul>
            {lists.can_edit_global && (
              <p className="text-xs text-subtle-foreground">
                You’re an admin: changes to this list apply to every account.
              </p>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
