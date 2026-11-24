import {
  flexRender, getCoreRowModel, useReactTable, type ColumnDef, type RowSelectionState, type VisibilityState,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ArrowUpDown, Bookmark, ChevronLeft, ChevronRight, Columns3, Download, Loader2, Search, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { adminApi, adminDownload, errMsg, qs, type Page } from "../lib/admin-api";
import { useAdmin } from "../lib/admin-context";
import { EmptyState, ErrorState, LoadingRows, Select } from "./page";

export type Filter = { key: string; label: string; options: { value: string; label: string }[] };
type View = { name: string; params: Record<string, string>; hidden: string[] };

declare module "@tanstack/react-table" {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData, TValue> {
    sortKey?: string;
    className?: string;
  }
}

const viewsKey = (id: string) => `aiwazz-admin-views:${id}`;
const colsKey = (id: string) => `aiwazz-admin-cols:${id}`;
const load = <T,>(k: string, d: T): T => {
  try { return JSON.parse(localStorage.getItem(k) ?? "") as T; } catch { return d; }
};

export function useList<T>(endpoint: string, params: Record<string, string | number>) {
  const [data, setData] = useState<Page<T> | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const key = endpoint + qs(params);
  const seq = useRef(0);
  const reload = useCallback(() => {
    const n = ++seq.current;
    setLoading(true);
    setError("");
    adminApi<Page<T>>(key).then(
      (d) => n === seq.current && (setData(d), setLoading(false)),
      (e) => n === seq.current && (setError(errMsg(e)), setLoading(false)),
    );
  }, [key]);
  useEffect(reload, [reload]);
  return { data, error, loading, reload };
}

export function DataTable<T extends { id: string | number }>({
  id, endpoint, columns, filters = [], defaultSort = "", searchPlaceholder = "Search…", onRowClick, exportName,
  extraParams = {}, toolbar, bulkActions, emptyTitle = "Nothing here yet", emptyHint, reloadKey, pageSize = 25, syncUrl = true,
}: {
  id: string;
  endpoint: string;
  columns: ColumnDef<T, unknown>[];
  filters?: Filter[];
  defaultSort?: string;
  searchPlaceholder?: string | null;
  onRowClick?: (row: T) => void;
  exportName?: string;
  extraParams?: Record<string, string>;
  toolbar?: ReactNode;
  bulkActions?: (rows: T[], done: () => void) => ReactNode;
  emptyTitle?: string;
  emptyHint?: ReactNode;
  reloadKey?: unknown;
  pageSize?: number;
  /** false: keep filters in local state (several tables on one page, e.g. user detail tabs). */
  syncUrl?: boolean;
}) {
  const { can } = useAdmin();
  const [urlSp, setUrlSp] = useSearchParams();
  const [localSp, setLocalSp] = useState(() => new URLSearchParams());
  const sp = syncUrl ? urlSp : localSp;
  const setSp = useCallback((fn: (p: URLSearchParams) => URLSearchParams, opts?: { replace?: boolean }) =>
    syncUrl ? setUrlSp(fn, opts) : setLocalSp((p) => fn(p)), [syncUrl, setUrlSp]);
  const known = ["q", "sort", "page", ...filters.map((f) => f.key)];
  const params: Record<string, string> = {};
  for (const k of known) if (sp.get(k)) params[k] = sp.get(k)!;
  const page = Number(params.page ?? 1) || 1;
  const sort = params.sort ?? defaultSort;
  const [q, setQ] = useState(params.q ?? "");
  const setParam = useCallback((patch: Record<string, string | null>) => {
    setSp((prev) => {
      const n = new URLSearchParams(prev);
      for (const [k, v] of Object.entries(patch)) (v ? n.set(k, v) : n.delete(k));
      if (!("page" in patch)) n.delete("page");
      return n;
    }, { replace: true });
  }, [setSp]);
  useEffect(() => {
    const t = setTimeout(() => (q !== (params.q ?? "") ? setParam({ q: q || null }) : undefined), 300);
    return () => clearTimeout(t);
  }, [q]); // eslint-disable-line react-hooks/exhaustive-deps

  const { data, error, loading, reload } = useList<T>(endpoint, { ...extraParams, ...params, sort, page, size: pageSize });
  useEffect(() => { if (reloadKey !== undefined) reload(); }, [reloadKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const [hidden, setHidden] = useState<VisibilityState>(() => load(colsKey(id), {}));
  useEffect(() => { try { localStorage.setItem(colsKey(id), JSON.stringify(hidden)); } catch { /* ignore */ } }, [hidden, id]);
  const [views, setViews] = useState<View[]>(() => load(viewsKey(id), []));
  const saveViews = (v: View[]) => { setViews(v); try { localStorage.setItem(viewsKey(id), JSON.stringify(v)); } catch { /* ignore */ } };
  const [selection, setSelection] = useState<RowSelectionState>({});
  useEffect(() => setSelection({}), [data]);

  const cols = useMemo<ColumnDef<T, unknown>[]>(() => !bulkActions ? columns : [{
    id: "_select", enableHiding: false,
    header: ({ table }) => (
      <input type="checkbox" aria-label="Select all on this page" className="size-4 accent-[var(--primary)]"
        checked={table.getIsAllRowsSelected()} onChange={table.getToggleAllRowsSelectedHandler()} />
    ),
    cell: ({ row }) => (
      <input type="checkbox" aria-label="Select row" className="size-4 accent-[var(--primary)]" checked={row.getIsSelected()}
        onClick={(e) => e.stopPropagation()} onChange={row.getToggleSelectedHandler()} />
    ),
  }, ...columns], [columns, bulkActions]);

  const table = useReactTable({
    data: data?.items ?? [], columns: cols, getCoreRowModel: getCoreRowModel(), manualPagination: true, manualSorting: true,
    state: { columnVisibility: hidden, rowSelection: selection }, onColumnVisibilityChange: setHidden,
    onRowSelectionChange: setSelection, getRowId: (r) => String(r.id), enableRowSelection: !!bulkActions,
  });
  const selected = table.getSelectedRowModel().rows.map((r) => r.original);
  const pages = data ? Math.max(1, Math.ceil(data.total / data.size)) : 1;
  const [exporting, setExporting] = useState(false);
  const exportCsv = async () => {
    setExporting(true);
    try {
      await adminDownload(endpoint + qs({ ...extraParams, ...params, sort, format: "csv" }), `aiwazz-${exportName}.csv`);
    } catch (e) {
      toast.error("Export failed", { description: errMsg(e) });
    } finally {
      setExporting(false);
    }
  };
  const activeFilters = filters.filter((f) => params[f.key]).length + (params.q ? 1 : 0);

  return (
    <div className="rounded-xl border bg-surface shadow-sm">
      <div className="flex flex-wrap items-center gap-2 border-b p-3">
        {searchPlaceholder !== null && (
          <div className="relative min-w-0 flex-1 sm:max-w-xs">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={searchPlaceholder} aria-label="Search" className="h-9 pl-8" />
          </div>
        )}
        {filters.map((f) => (
          <Select key={f.key} aria-label={f.label} value={params[f.key] ?? ""} onChange={(e) => setParam({ [f.key]: e.target.value || null })}>
            <option value="">{f.label}: all</option>
            {f.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </Select>
        ))}
        {activeFilters > 0 && (
          <Button variant="ghost" size="sm" onClick={() => (setQ(""), setParam(Object.fromEntries(known.map((k) => [k, null]))))}>
            <X /> Clear
          </Button>
        )}
        <div className="ml-auto flex items-center gap-1.5">
          {toolbar}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" aria-label="Saved views"><Bookmark /> <span className="hidden sm:inline">Views</span></Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <DropdownMenuLabel>Saved views (this browser)</DropdownMenuLabel>
              {views.length === 0 && <p className="px-2 py-1.5 text-xs text-muted-foreground">No saved views yet.</p>}
              {views.map((v) => (
                <DropdownMenuItem key={v.name} onSelect={() => {
                  setQ(v.params.q ?? "");
                  setParam(Object.fromEntries(known.map((k) => [k, v.params[k] ?? null])));
                  setHidden(Object.fromEntries(v.hidden.map((h) => [h, false])));
                }}>
                  <span className="truncate">{v.name}</span>
                  <button type="button" aria-label={`Delete view ${v.name}`} className="ml-auto text-muted-foreground hover:text-danger"
                    onClick={(e) => (e.stopPropagation(), e.preventDefault(), saveViews(views.filter((x) => x.name !== v.name)))}>
                    <Trash2 className="size-3.5" />
                  </button>
                </DropdownMenuItem>
              ))}
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => {
                const name = window.prompt("Name this view", "My view")?.trim();
                if (!name) return;
                const hiddenCols = Object.entries(hidden).filter(([, v]) => v === false).map(([k]) => k);
                saveViews([...views.filter((v) => v.name !== name), { name, params: { ...params, sort }, hidden: hiddenCols }]);
                toast.success(`Saved view "${name}"`);
              }}>
                <Bookmark /> Save current view…
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" aria-label="Choose columns"><Columns3 /> <span className="hidden sm:inline">Columns</span></Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {table.getAllLeafColumns().filter((c) => c.getCanHide()).map((c) => (
                <DropdownMenuCheckboxItem key={c.id} checked={c.getIsVisible()} onCheckedChange={(v) => c.toggleVisibility(!!v)}
                  onSelect={(e) => e.preventDefault()}>
                  {typeof c.columnDef.header === "string" ? c.columnDef.header : c.id}
                </DropdownMenuCheckboxItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
          {exportName && can("export") && (
            <Button variant="outline" size="sm" onClick={exportCsv} disabled={exporting} title="Export CSV (asks you to confirm it's you)">
              {exporting ? <Loader2 className="animate-spin" /> : <Download />} <span className="hidden sm:inline">CSV</span>
            </Button>
          )}
        </div>
      </div>

      {bulkActions && selected.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 border-b bg-surface-2/50 px-3 py-2 text-sm">
          <span className="font-medium">{selected.length} selected</span>
          {bulkActions(selected, () => (setSelection({}), reload()))}
        </div>
      )}

      {error ? <ErrorState message={error} onRetry={reload} /> : !data && loading ? <LoadingRows /> : (
        <div className={cn("relative overflow-x-auto", loading && "opacity-60 transition-opacity")}>
          {data && data.items.length === 0 ? (
            <EmptyState title={activeFilters ? "No matches" : emptyTitle} hint={activeFilters ? "Try other filters." : emptyHint} />
          ) : (
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                {table.getHeaderGroups().map((hg) => (
                  <tr key={hg.id} className="border-b text-left text-xs text-muted-foreground">
                    {hg.headers.map((h) => {
                      const sk = h.column.columnDef.meta?.sortKey;
                      const dir = sk && (sort === sk ? "asc" : sort === `-${sk}` ? "desc" : null);
                      return (
                        <th key={h.id} scope="col" className={cn("px-3 py-2.5 font-medium whitespace-nowrap", h.column.columnDef.meta?.className)}
                          aria-sort={dir === "asc" ? "ascending" : dir === "desc" ? "descending" : undefined}>
                          {sk ? (
                            <button type="button" className="inline-flex items-center gap-1 hover:text-foreground"
                              onClick={() => setParam({ sort: dir === "desc" ? sk : `-${sk}` })}>
                              {flexRender(h.column.columnDef.header, h.getContext())}
                              {dir === "asc" ? <ArrowUp className="size-3" /> : dir === "desc" ? <ArrowDown className="size-3" /> : <ArrowUpDown className="size-3 opacity-50" />}
                            </button>
                          ) : flexRender(h.column.columnDef.header, h.getContext())}
                        </th>
                      );
                    })}
                  </tr>
                ))}
              </thead>
              <tbody>
                {table.getRowModel().rows.map((r) => (
                  <tr key={r.id} onClick={onRowClick ? () => onRowClick(r.original) : undefined}
                    onKeyDown={onRowClick ? (e) => e.key === "Enter" && onRowClick(r.original) : undefined}
                    tabIndex={onRowClick ? 0 : undefined}
                    className={cn("border-b last:border-0", onRowClick && "cursor-pointer hover:bg-surface-2/60 focus-visible:bg-surface-2/60 focus-visible:outline-none")}>
                    {r.getVisibleCells().map((c) => (
                      <td key={c.id} className={cn("px-3 py-2.5 align-middle", c.column.columnDef.meta?.className)}>
                        {flexRender(c.column.columnDef.cell, c.getContext())}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {data && data.total > 0 && (
        <div className="flex items-center justify-between gap-2 border-t px-3 py-2 text-xs text-muted-foreground">
          <span className="tabular">
            {(data.page - 1) * data.size + 1}–{Math.min(data.total, data.page * data.size)} of {data.total.toLocaleString("en-IN")}
          </span>
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="icon-sm" aria-label="Previous page" disabled={page <= 1} onClick={() => setParam({ page: String(page - 1) })}><ChevronLeft /></Button>
            <span className="tabular">Page {page} / {pages}</span>
            <Button variant="ghost" size="icon-sm" aria-label="Next page" disabled={page >= pages} onClick={() => setParam({ page: String(page + 1) })}><ChevronRight /></Button>
          </div>
        </div>
      )}
    </div>
  );
}
