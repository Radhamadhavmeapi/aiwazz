/** Before → after view of an audit entry (JSON objects with only the changed keys). */
export function JsonDiff({ before, after }: { before: string | null; after: string | null }) {
  const parse = (s: string | null): Record<string, unknown> | null => {
    if (!s) return null;
    try {
      const v = JSON.parse(s);
      return v && typeof v === "object" && !Array.isArray(v) ? v : { value: v };
    } catch {
      return { value: s };
    }
  };
  const b = parse(before);
  const a = parse(after);
  const keys = [...new Set([...Object.keys(b ?? {}), ...Object.keys(a ?? {})])];
  if (!keys.length) return <p className="text-xs text-muted-foreground">No field changes recorded.</p>;
  const show = (v: unknown) => (v === undefined ? "–" : typeof v === "string" ? v : JSON.stringify(v));
  return (
    <table className="w-full text-xs">
      <thead>
        <tr className="text-left text-muted-foreground">
          <th className="py-1 pr-2 font-medium">Field</th>
          <th className="py-1 pr-2 font-medium">Before</th>
          <th className="py-1 font-medium">After</th>
        </tr>
      </thead>
      <tbody className="font-mono">
        {keys.map((k) => (
          <tr key={k} className="border-t align-top">
            <td className="py-1.5 pr-2 font-sans font-medium">{k}</td>
            <td className="py-1.5 pr-2 break-all text-danger">{b ? show(b[k]) : "–"}</td>
            <td className="py-1.5 break-all text-success">{a ? show(a[k]) : "–"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
