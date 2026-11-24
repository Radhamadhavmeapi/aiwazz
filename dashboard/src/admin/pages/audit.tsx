import type { ColumnDef } from "@tanstack/react-table";
import { useState } from "react";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { DataTable } from "../components/data-table";
import { JsonDiff } from "../components/json-diff";
import { fmtDate, PageHeader, Pill } from "../components/page";
import { AdminShell } from "../components/shell";

export type AuditRow = {
  id: number; at: string; actor_id: number | null; actor_email: string; actor_role: string; action: string;
  target_type: string; target_id: string; target_label: string; before: string | null; after: string | null;
  reason: string; ip: string; user_agent: string;
};

const tone = (a: string) =>
  a.endsWith(".fail") || a.includes("delete") || a.includes("refund") ? "red" : a.startsWith("mfa") || a.startsWith("stepup") ? "blue" : "gray";

export const auditColumns: ColumnDef<AuditRow, unknown>[] = [
  { id: "at", header: "Time (IST)", meta: { sortKey: "at", className: "whitespace-nowrap" }, cell: ({ row }) => <span className="tabular text-xs">{fmtDate(row.original.at)}</span> },
  { id: "actor", header: "Actor", meta: { sortKey: "actor" }, cell: ({ row }) => (
    <div className="min-w-0"><p className="truncate">{row.original.actor_email}</p><p className="text-xs text-muted-foreground capitalize">{row.original.actor_role}</p></div>
  ) },
  { id: "action", header: "Action", meta: { sortKey: "action" }, cell: ({ row }) => <Pill tone={tone(row.original.action)} className="font-mono">{row.original.action}</Pill> },
  { id: "target", header: "Target", cell: ({ row }) => row.original.target_type ? (
    <span className="text-xs"><span className="text-muted-foreground">{row.original.target_type}</span> {row.original.target_label || `#${row.original.target_id}`}</span>
  ) : "–" },
  { id: "reason", header: "Reason", cell: ({ row }) => <span className="line-clamp-1 text-xs text-muted-foreground">{row.original.reason || "–"}</span> },
  { id: "ip", header: "IP", cell: ({ row }) => <span className="font-mono text-xs">{row.original.ip || "–"}</span> },
];

export function AuditDetail({ row, onClose }: { row: AuditRow | null; onClose: () => void }) {
  return (
    <Sheet open={!!row} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-lg">
        <SheetHeader>
          <SheetTitle className="font-mono text-base">{row?.action}</SheetTitle>
          <SheetDescription>Entry #{row?.id} · {fmtDate(row?.at)} IST · append-only, can't be edited</SheetDescription>
        </SheetHeader>
        {row && (
          <div className="space-y-5 px-4 pb-6 text-sm">
            <dl className="grid grid-cols-[110px_1fr] gap-x-3 gap-y-2">
              <dt className="text-muted-foreground">Actor</dt><dd className="break-all">{row.actor_email} ({row.actor_role})</dd>
              <dt className="text-muted-foreground">Target</dt><dd className="break-all">{row.target_type ? `${row.target_type} #${row.target_id} ${row.target_label}` : "–"}</dd>
              <dt className="text-muted-foreground">Reason</dt><dd>{row.reason || "–"}</dd>
              <dt className="text-muted-foreground">IP</dt><dd className="font-mono">{row.ip || "–"}</dd>
              <dt className="text-muted-foreground">Browser</dt><dd className="text-xs break-all text-muted-foreground">{row.user_agent || "–"}</dd>
            </dl>
            <div>
              <h3 className="mb-2 text-xs font-semibold">Changes</h3>
              <JsonDiff before={row.before} after={row.after} />
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}

const ACTIONS = [
  ["mfa", "2FA"], ["stepup", "Step-up"], ["admin", "Admin sessions"], ["user", "Users"], ["invite", "Invites"],
  ["billing", "Billing"], ["plan", "Plans"], ["coupon", "Coupons"], ["support", "Support"], ["moderation", "Moderation"],
  ["voice", "Voices"], ["pronunciation", "Pronunciations"], ["queue", "Queue"], ["system", "System"], ["settings", "Settings"],
  ["team", "Team"], ["legal", "Legal"], ["export", "Exports"], ["impersonate", "Impersonation"],
].map(([value, label]) => ({ value, label }));

export default function AuditPage() {
  const [open, setOpen] = useState<AuditRow | null>(null);
  return (
    <AdminShell title="Audit log">
      <PageHeader title="Audit log" description="Every staff action, with who, when, from where and what changed. Append-only: nobody can edit or delete entries, not even the owner." />
      <DataTable<AuditRow> id="audit" endpoint="/api/admin/audit" columns={auditColumns} defaultSort="" exportName="audit"
        searchPlaceholder="Search action, target, reason…" onRowClick={setOpen}
        filters={[{ key: "action", label: "Area", options: ACTIONS }]} emptyTitle="No audit entries yet" />
      <AuditDetail row={open} onClose={() => setOpen(null)} />
    </AdminShell>
  );
}
