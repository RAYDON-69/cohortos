/**
 * Global smart search — tabs/features + students (desk-wide).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listStudentsApi, loadTokens } from "../api/client";
import "./GlobalSearch.css";

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
    <div className="global-search" ref={ref} data-testid="global-search">
      <label className="sr-only" htmlFor="global-search-input">
        Search tabs, features, students
      </label>
      <input
        id="global-search-input"
        className="global-search-input"
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
        <ul className="global-search-results" role="listbox">
          {hits.length === 0 && (
            <li className="global-search-empty caption muted">No matches</li>
          )}
          {hits.map((h, i) => (
            <li key={h.kind + h.path + i} role="option">
              <button
                type="button"
                className="global-search-hit"
                onClick={() => {
                  navigate(h.path);
                  setQ("");
                  setOpen(false);
                }}
              >
                <span className="global-search-kind">{h.kind}</span>
                <span className="global-search-label">{h.label}</span>
                {h.sub && <span className="caption muted">{h.sub}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
