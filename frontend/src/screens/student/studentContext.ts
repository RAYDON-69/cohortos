/**
 * Demo / session context for student surfaces (Portion 21).
 * In production these come from account link + JWT claims.
 */

const KEYS = {
  accountId: "cohortos_student_account_id",
  studentId: "cohortos_student_admission_id",
  studentName: "cohortos_student_name",
  roll: "cohortos_student_roll",
};

export function loadStudentSession(): {
  accountId: string;
  studentId: string;
  studentName: string;
  roll: string;
} {
  return {
    accountId: localStorage.getItem(KEYS.accountId) || "",
    studentId: localStorage.getItem(KEYS.studentId) || "",
    studentName: localStorage.getItem(KEYS.studentName) || "",
    roll: localStorage.getItem(KEYS.roll) || "",
  };
}

export function saveStudentSession(s: {
  accountId: string;
  studentId: string;
  studentName?: string;
  roll?: string;
}) {
  localStorage.setItem(KEYS.accountId, s.accountId);
  localStorage.setItem(KEYS.studentId, s.studentId);
  if (s.studentName != null) localStorage.setItem(KEYS.studentName, s.studentName);
  if (s.roll != null) localStorage.setItem(KEYS.roll, s.roll);
}

export function clearStudentSession() {
  Object.values(KEYS).forEach((k) => localStorage.removeItem(k));
}

/** Map access-rule machine reasons → plain language for the student. */
export function plainAccessReason(reasons: string[]): string {
  if (!reasons.length) return "Locked by centre rules.";
  const map: Record<string, string> = {
    not_paid_up: "Unlocks after your next paid month",
    no_exam_results: "Unlocks after you sit your next exam",
    did_not_sit_last_exam: "Unlocks after you sit your next exam",
    resource_not_found_or_inactive: "This resource is no longer available",
    always_deny: "This resource is not available to students",
  };
  for (const r of reasons) {
    if (map[r]) return map[r];
    if (r.startsWith("attendance_") && r.includes("_lt_")) {
      return "Unlocks when your attendance meets the required percentage";
    }
    if (r.startsWith("expired_on_")) {
      return `This resource expired on ${r.replace("expired_on_", "")}`;
    }
  }
  return reasons.join(" · ");
}
