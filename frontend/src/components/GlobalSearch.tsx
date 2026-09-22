/**
 * Global smart search — tabs/features + students (desk-wide).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listStudentsApi, loadTokens } from "../api/client";

type Hit = { kind: "tab" | "feature" | "student"; label: string; path: string; sub?: string };

const TABS: Hit[] = [
  { kind: "tab", label: "Attendance", path: "/attendance" },
  { kind: "tab", label: "Attendance history", path: "/attendance/history" },
  { kind: "tab", label: "Admissions", path: "/admissions" },
  { kind: "tab", label: "Batches", path: "/batches" },
  { kind: "tab", label: "Fees", path: "/fees" },
  { kind: "tab", label: "Fee reminders", path: "/fees/nag" },
  { kind: "tab", label: "Exams", path: "/exams" },
  { kind: "tab", label: "Analytics", path: "/exams/analytics" },
  { kind: "tab", label: "Vault", path: "/vault" },
  { kind: "tab", label: "Settings", path: "/settings" },
];

const FEATURES: Hit[] = [
  { kind: "feature", label: "Staff & roles", path: "/settings/staff" },
  { kind: "feature", label: "Biometric devices", path: "/settings/biometric" },
  { kind: "feature", label: "File storage", path: "/settings/storage" },
  { kind: "feature", label: "Backup & export", path: "/settings/backup" },
  { kind: "feature", label: "Sync conflicts", path: "/settings/conflicts" },
  { kind: "feature", label: "Support & legal", path: "/support" },
  { kind: "feature", label: "Centre setup wizard", path: "/setup" },
];

export function GlobalSearch() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [students, setStudents] = useState<Hit[]>([]);
  const ref = useRef<HTMLDivElement>(null);

  const loadStudents = useCallback(async () => {
    const tid = loadTokens().tenant_id;
    if (!tid) return;
    try {
      const res = await listStudentsApi(tid);
      setStudents(
        (res.students || []).slice(0, 200).map((s: { id?: string; name?: string; roll?: string }) => ({
          kind: "student" as const,
          label: s.name || "Student",
          sub: s.roll ? `Roll ${s.roll}` : undefined,
          path: `/admissions?highlight=${encodeURIComponent(String(s.id || ""))}`,
        }))
      );
    } catch {
      /* offline — keep prior */
    }
  }, []);

  useEffect(() => {
    void loadStudents();
  }, [loadStudents]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const hits = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return [] as Hit[];
    const match = (h: Hit) =>
      h.label.toLowerCase().includes(needle) || (h.sub || "").toLowerCase().includes(needle);
    return [
      ...TABS.filter(match).slice(0, 5),
      ...FEATURES.filter(match).slice(0, 5),
      ...students.filter(match).slice(0, 8),
    ];
  }, [q, students]);

  return (
    <div className="relative w-full max-w-md" ref={ref} data-testid="global-search">
      <label className="sr-only" htmlFor="global-search-input">
        Search tabs, features, students
      </label>
      <input
        id="global-search-input"
        className="h-10 w-full rounded-md border border-border-strong bg-cream px-3 text-sm text-ink placeholder:text-slate-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-peri-300"
        type="search"
        placeholder="Search tabs, features, students…"
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        autoComplete="off"
      />
      {open && q.trim() && (
        <ul
          className="absolute z-50 mt-1 max-h-72 w-full overflow-auto rounded-card border border-border bg-white py-1 shadow-soft"
          role="listbox"
        >
          {hits.length === 0 && (
            <li className="px-3 py-2 text-xs text-slate-500">No matches</li>
          )}
          {hits.map((h, i) => (
            <li key={h.kind + h.path + i} role="option">
              <button
                type="button"
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-sage-100"
                onClick={() => {
                  navigate(h.path);
                  setQ("");
                  setOpen(false);
                }}
              >
                <span className="text-[10px] font-semibold uppercase text-slate-500">{h.kind}</span>
                <span className="font-medium text-ink">{h.label}</span>
                {h.sub && <span className="text-xs text-slate-500">{h.sub}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
