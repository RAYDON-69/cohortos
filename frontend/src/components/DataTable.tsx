import React, { useMemo, useState } from "react";
import "./DataTable.css";

export interface Column<T> {
  key: string;
  header: string;
  sortable?: boolean;
  /** Mobile: keep this column when ≤760px */
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

/**
 * Data table §4.3 — sortable, skeleton loading, empty state, 25/50/100 pagination.
 * Headers stay visible while skeleton rows load.
 */
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
    const col = columns.find((c) => c.key === sortKey);
    if (!col) return rows;
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
  }, [rows, sortKey, sortDir, columns]);

  const pageCount = Math.max(1, Math.ceil(sorted.length / pageSize));
  const safePage = Math.min(page, pageCount - 1);
  const pageRows = sorted.slice(safePage * pageSize, safePage * pageSize + pageSize);

  const onHeaderClick = (col: Column<T>) => {
    if (!col.sortable) return;
    if (sortKey === col.key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(col.key);
      setSortDir("asc");
    }
  };

  return (
    <div className={`data-table-wrap ${className}`}>
      <div className="data-table-scroll">
        <div className="data-table" role="table" aria-busy={loading || undefined}>
          <div className="data-table-head" role="row">
            {columns.map((col) => (
              <div
                key={col.key}
                className={`data-table-th ${col.essential ? "essential" : "optional"} ${col.sortable ? "sortable" : ""}`}
                role="columnheader"
                style={col.width ? { flex: `0 0 ${col.width}` } : undefined}
                tabIndex={col.sortable ? 0 : undefined}
                onClick={() => onHeaderClick(col)}
                onKeyDown={(e) => {
                  if (col.sortable && (e.key === "Enter" || e.key === " ")) {
                    e.preventDefault();
                    onHeaderClick(col);
                  }
                }}
                aria-sort={
                  sortKey === col.key ? (sortDir === "asc" ? "ascending" : "descending") : undefined
                }
              >
                {col.header}
                {col.sortable && sortKey === col.key && (
                  <span className="sort-chevron" aria-hidden="true">
                    {sortDir === "asc" ? " ↑" : " ↓"}
                  </span>
                )}
              </div>
            ))}
          </div>

          {loading && (
            <div className="data-table-body" role="rowgroup">
              {[0, 1, 2, 3, 4].map((i) => (
                <div key={i} className="data-table-row skeleton-row" role="row">
                  {columns.map((col) => (
                    <div
                      key={col.key}
                      className={`data-table-td ${col.essential ? "essential" : "optional"}`}
                      role="cell"
                    >
                      <div className="skeleton-bar" />
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}

          {!loading && pageRows.length === 0 && (
            <div className="data-table-empty">
              <div className="empty-title">{emptyTitle}</div>
              {emptyBody && <div className="empty-body">{emptyBody}</div>}
              {emptyAction && <div className="empty-action">{emptyAction}</div>}
            </div>
          )}

          {!loading && pageRows.length > 0 && (
            <div className="data-table-body">
              {pageRows.map((row) => (
                <div
                  key={rowKey(row)}
                  className={`data-table-row ${onRowClick ? "clickable" : ""}`}
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
                      className={`data-table-td ${col.essential ? "essential" : "optional"}`}
                      role="cell"
                      style={col.width ? { flex: `0 0 ${col.width}` } : undefined}
                    >
                      {col.render ? col.render(row) : String((row as any)[col.key] ?? "")}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {!loading && sorted.length > 0 && (
        <div className="data-table-footer">
          <div className="data-table-page-size">
            <label>
              Rows
              <select
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
          </div>
          <div className="data-table-pager">
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              disabled={safePage <= 0}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
            >
              Prev
            </button>
            <span className="caption">
              {safePage + 1} / {pageCount}
            </span>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
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
