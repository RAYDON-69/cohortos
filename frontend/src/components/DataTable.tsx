import React, { useMemo, useState } from "react";
import { cn } from "../lib/utils";

export interface Column<T> {
  key: string;
  header: string;
  sortable?: boolean;
  essential?: boolean;
  render?: (row: T) => React.ReactNode;
  width?: string;
}

export interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  loading?: boolean;
  emptyTitle?: string;
  emptyBody?: string;
  emptyAction?: React.ReactNode;
  pageSizeOptions?: number[];
  defaultPageSize?: number;
  onRowClick?: (row: T) => void;
  className?: string;
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  loading = false,
  emptyTitle = "Nothing here yet",
  emptyBody,
  emptyAction,
  pageSizeOptions = [25, 50, 100],
  defaultPageSize = 25,
  onRowClick,
  className = "",
}: DataTableProps<T>) {
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(defaultPageSize);

  const sorted = useMemo(() => {
    if (!sortKey) return rows;
    const copy = [...rows];
    copy.sort((a, b) => {
      const av = (a as any)[sortKey];
      const bv = (b as any)[sortKey];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      const cmp = String(av).localeCompare(String(bv), undefined, { numeric: true });
      return sortDir === "asc" ? cmp : -cmp;
    });
    return copy;
  }, [rows, sortKey, sortDir]);

  const pageCount = Math.max(1, Math.ceil(sorted.length / pageSize));
  const safePage = Math.min(page, pageCount - 1);
  const pageRows = sorted.slice(safePage * pageSize, safePage * pageSize + pageSize);

  const onHeaderClick = (col: Column<T>) => {
    if (!col.sortable) return;
    if (sortKey === col.key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(col.key);
      setSortDir("asc");
    }
  };

  return (
    <div className={cn("overflow-hidden rounded-card border border-border bg-white", className)}>
      <div className="overflow-x-auto">
        <div role="table" aria-busy={loading || undefined} className="min-w-full">
          <div className="sticky top-0 z-[1] flex bg-sage-100 border-b border-border" role="row">
            {columns.map((col) => (
              <div
                key={col.key}
                role="columnheader"
                className={cn(
                  "flex-1 min-w-0 px-4 py-2 text-[10px] font-semibold uppercase tracking-wide text-sage-700",
                  col.sortable && "cursor-pointer select-none hover:text-sage-900",
                  !col.essential && "hidden md:block"
                )}
                style={col.width ? { flex: `0 0 ${col.width}` } : undefined}
                tabIndex={col.sortable ? 0 : undefined}
                onClick={() => onHeaderClick(col)}
                onKeyDown={(e) => {
                  if (col.sortable && (e.key === "Enter" || e.key === " ")) {
                    e.preventDefault();
                    onHeaderClick(col);
                  }
                }}
                aria-sort={sortKey === col.key ? (sortDir === "asc" ? "ascending" : "descending") : undefined}
              >
                {col.header}
                {col.sortable && sortKey === col.key && (
                  <span aria-hidden="true">{sortDir === "asc" ? " ↑" : " ↓"}</span>
                )}
              </div>
            ))}
          </div>

          {loading &&
            [0, 1, 2, 3, 4].map((i) => (
              <div key={i} className="flex border-b border-border animate-pulse" role="row">
                {columns.map((col) => (
                  <div
                    key={col.key}
                    className={cn("flex-1 px-4 py-3", !col.essential && "hidden md:block")}
                    role="cell"
                  >
                    <div className="h-3 rounded bg-sage-100" />
                  </div>
                ))}
              </div>
            ))}

          {!loading && pageRows.length === 0 && (
            <div className="px-4 py-10 text-center text-sm text-slate-700">
              <div className="font-semibold text-ink">{emptyTitle}</div>
              {emptyBody && <div className="mt-1">{emptyBody}</div>}
              {emptyAction && <div className="mt-3">{emptyAction}</div>}
            </div>
          )}

          {!loading &&
            pageRows.map((row) => (
              <div
                key={rowKey(row)}
                className={cn(
                  "flex items-center border-b border-border last:border-0",
                  onRowClick && "cursor-pointer hover:bg-sage-100/60"
                )}
                role="row"
                tabIndex={onRowClick ? 0 : undefined}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                onKeyDown={
                  onRowClick
                    ? (e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          onRowClick(row);
                        }
                      }
                    : undefined
                }
              >
                {columns.map((col) => (
                  <div
                    key={col.key}
                    className={cn("flex-1 min-w-0 px-4 py-3 text-sm text-ink", !col.essential && "hidden md:block")}
                    role="cell"
                    style={col.width ? { flex: `0 0 ${col.width}` } : undefined}
                  >
                    {col.render ? col.render(row) : String((row as any)[col.key] ?? "")}
                  </div>
                ))}
              </div>
            ))}
        </div>
      </div>

      {!loading && sorted.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border px-3 py-2 text-sm">
          <label className="flex items-center gap-2 text-slate-700">
            Rows
            <select
              className="rounded border border-border-strong bg-cream px-2 py-1"
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value));
                setPage(0);
              }}
            >
              {pageSizeOptions.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="text-sage-700 font-semibold disabled:opacity-40"
              disabled={safePage <= 0}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
            >
              Prev
            </button>
            <span className="text-slate-700">
              {safePage + 1} / {pageCount}
            </span>
            <button
              type="button"
              className="text-sage-700 font-semibold disabled:opacity-40"
              disabled={safePage >= pageCount - 1}
              onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
