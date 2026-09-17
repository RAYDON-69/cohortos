/** Shared Owner/Desk navigation — every main screen uses the same items. */
export type DeskNavItem = {
  id: string;
  label: string;
  active?: boolean;
  onClick?: () => void;
};

export function buildDeskNav(
  navigate: (path: string) => void,
  activeId: string,
  labels?: Partial<Record<string, string>>,
  role?: string,
): DeskNavItem[] {
  const L = {
    attendance: labels?.attendance ?? "Attendance",
    history: labels?.history ?? "History",
    admissions: labels?.admissions ?? "Admissions",
    batches: labels?.batches ?? "Batches",
    fees: labels?.fees ?? "Fees",
    nag: labels?.nag ?? "Fee reminders",
    exams: labels?.exams ?? "Exams",
    analytics: labels?.analytics ?? "Analytics",
    vault: labels?.vault ?? "Vault",
    settings: labels?.settings ?? "Settings",
    staff: labels?.staff ?? "Staff",
    messaging: labels?.messaging ?? "Messaging",
    mode: labels?.mode ?? "Mode",
    biometric: labels?.biometric ?? "Biometric",
    storage: labels?.storage ?? "Storage",
    conflicts: labels?.conflicts ?? "Conflicts",
    backup: labels?.backup ?? "Backup",
  };
  const items: { id: string; path: string; label: string; roles?: string[] }[] = [
    { id: "attendance", path: "/attendance", label: L.attendance },
    { id: "history", path: "/attendance/history", label: L.history },
    { id: "admissions", path: "/admissions", label: L.admissions },
    { id: "batches", path: "/batches", label: L.batches },
    { id: "fees", path: "/fees", label: L.fees },
    { id: "nag", path: "/fees/nag", label: L.nag },
    { id: "exams", path: "/exams", label: L.exams },
    { id: "analytics", path: "/exams/analytics", label: L.analytics },
    { id: "vault", path: "/vault", label: L.vault },
    { id: "settings", path: "/settings", label: L.settings },
    { id: "staff", path: "/settings/staff", label: L.staff, roles: ["owner"] },
    { id: "messaging", path: "/settings/messaging", label: L.messaging },
    { id: "mode", path: "/settings/mode", label: L.mode },
    { id: "biometric", path: "/settings/biometric", label: L.biometric },
    { id: "storage", path: "/settings/storage", label: L.storage, roles: ["owner"] },
    { id: "conflicts", path: "/settings/conflicts", label: L.conflicts, roles: ["owner"] },
    { id: "backup", path: "/settings/backup", label: L.backup, roles: ["owner"] },
  ];
  const roleNorm = (role || "").toLowerCase();
  return items
    .filter((it) => {
      if (!it.roles || it.roles.length === 0) return true;
      if (!roleNorm) return true;
      return it.roles.includes(roleNorm);
    })
    .map((it) => ({
      id: it.id,
      label: it.label,
      active: it.id === activeId,
      onClick: it.id === activeId ? undefined : () => navigate(it.path),
    }));
}

/** Teacher-focused nav — insight suite + core classroom surfaces. */
export function buildTeacherNav(
  navigate: (path: string) => void,
  activeId: string,
  labels?: Partial<Record<string, string>>,
): DeskNavItem[] {
  const L = {
    insight: labels?.insight ?? "Insight",
    itemBank: labels?.itemBank ?? "Item bank",
    style: labels?.style ?? "Style",
    threads: labels?.threads ?? "Flagged",
    review: labels?.review ?? "Review",
    ocr: labels?.ocr ?? "OCR",
    attendance: labels?.attendance ?? "Attendance",
    exams: labels?.exams ?? "Exams",
    vault: labels?.vault ?? "Vault",
  };
  const items: { id: string; path: string; label: string }[] = [
    { id: "insight", path: "/teacher/insight", label: L.insight },
    { id: "item-bank", path: "/teacher/item-bank", label: L.itemBank },
    { id: "style", path: "/teacher/style", label: L.style },
    { id: "threads", path: "/teacher/threads", label: L.threads },
    { id: "review", path: "/teacher/review", label: L.review },
    { id: "ocr", path: "/teacher/ocr", label: L.ocr },
    { id: "attendance", path: "/attendance", label: L.attendance },
    { id: "exams", path: "/exams", label: L.exams },
    { id: "vault", path: "/vault", label: L.vault },
  ];
  return items.map((it) => ({
    id: it.id,
    label: it.label,
    active: it.id === activeId,
    onClick: it.id === activeId ? undefined : () => navigate(it.path),
  }));
}
