/**
 * Screen-level axe a11y — Batches 1–5 Coaching-Centre Panel surfaces.
 * Heavy modules mocked so the suite stays memory-safe on constrained hosts.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { axe } from "vitest-axe";

vi.mock("../i18n/LocaleContext", () => ({
  useLocale: () => ({ t: (k: string) => k, locale: "en" }),
  LocaleProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock("../shell/AppShell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="shell">{children}</div>
  ),
}));
vi.mock("../nav/deskNav", () => ({ buildDeskNav: () => [] }));
vi.mock("../hooks/useTenant", () => ({
  useTenant: () => ({ tenantId: "t-1", role: "owner" }),
}));
vi.mock("../hooks/useConnectivity", () => ({
  useConnectivity: () => ({
    state: "synced",
    isOffline: false,
    isSyncing: false,
    isSynced: true,
    hasConflict: false,
  }),
}));
vi.mock("../hooks/useLicenseLockout", () => ({
  useLicenseLockout: () => ({
    locked: false,
    reason: null,
    loading: false,
    refresh: async () => {},
  }),
}));
vi.mock("../api/client", () => ({
  loadTokens: () => ({ tenant_id: "t-1", access_token: "x" }),
  listBatches: vi.fn(async () => ({ batches: [] })),
  listStudentsApi: vi.fn(async () => ({ students: [] })),
  listStudents: vi.fn(async () => ({ students: [] })),
  listExams: vi.fn(async () => ({ exams: [] })),
  listExamTemplates: vi.fn(async () => ({ templates: [] })),
  getExamAnalytics: vi.fn(async () => ({ rows: [] })),
  getTopicHeatmap: vi.fn(async () => ({ topics: [] })),
  getStruggleList: vi.fn(async () => ({ students: [] })),
  listVault: vi.fn(async () => ({ items: [] })),
  listVaultItems: vi.fn(async () => ({ items: [] })),
  listSyncConflicts: vi.fn(async () => ({ conflicts: [] })),
  getBackupStatus: vi.fn(async () => ({ last_backup_at: null, memory_usage: {}, backups: [] })),
  getBiometricStatus: vi.fn(async () => ({ pyzk_available: true, devices: [] })),
  getStorageSettings: vi.fn(async () => ({
    provider: "google_drive",
    configured: false,
    options: ["google_drive", "local_fs"],
  })),
  getSetupStatus: vi.fn(async () => ({
    needs_wizard: true,
    batch_count: 0,
    student_count: 0,
    steps: { centre: true, first_batch: false, first_admission: false, done: false },
  })),
  listStaff: vi.fn(async () => ({ staff: [] })),
  listPayments: vi.fn(async () => ({ rows: [] })),
  getAttendanceToday: vi.fn(async () => ({ rows: [] })),
  listAttendance: vi.fn(async () => ({ rows: [] })),
  getNagList: vi.fn(async () => ({ green: [], white: [], irregular: [] })),
  getMessagingSettings: vi.fn(async () => ({})),
  getModeSettings: vi.fn(async () => ({ mode: "offline-first" })),
  apiRequest: vi.fn(async () => ({})),
  tenantPath: (t: string, s: string) => `/t/${t}${s}`,
}));

async function expectNoSeriousAxe(container: HTMLElement) {
  // Let useEffect data loads settle into empty/error UI before axe
  await waitFor(() => {
    expect(container.querySelector("[aria-busy=true]") || container).toBeTruthy();
  });
  await new Promise((r) => setTimeout(r, 30));
  const results = await axe(container);
  const serious = results.violations.filter(
    (v) => v.impact === "critical" || v.impact === "serious"
  );
  if (serious.length) {
    // eslint-disable-next-line no-console
    console.error(
      serious.map((v) => `${v.id}: ${v.help} — ${v.nodes[0]?.html?.slice(0, 120)}`).join("\n")
    );
  }
  expect(serious).toEqual([]);
}

function wrap(ui: React.ReactNode) {
  return <MemoryRouter>{ui}</MemoryRouter>;
}

describe("Batch 1–5 screens a11y", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("ConflictLog empty", async () => {
    const { ConflictLogScreen } = await import("./settings/ConflictLog");
    const { container } = render(wrap(<ConflictLogScreen />));
    await expectNoSeriousAxe(container);
  });

  it("BackupExport", async () => {
    const { BackupExportScreen } = await import("./settings/BackupExport");
    const { container } = render(wrap(<BackupExportScreen />));
    await expectNoSeriousAxe(container);
  });

  it("BiometricDevices empty", async () => {
    const { BiometricDevicesScreen } = await import("./settings/BiometricDevices");
    const { container } = render(wrap(<BiometricDevicesScreen />));
    await expectNoSeriousAxe(container);
  });

  it("StorageProvider settings UI", async () => {
    const { StorageProviderScreen } = await import("./settings/StorageProvider");
    const { container } = render(wrap(<StorageProviderScreen />));
    await expectNoSeriousAxe(container);
  });

  it("StaffRoles", async () => {
    const { StaffRolesScreen } = await import("./settings/StaffRoles");
    const { container } = render(wrap(<StaffRolesScreen />));
    await expectNoSeriousAxe(container);
  });

  it("CentreSetupWizard empty (no batches)", async () => {
    const { CentreSetupWizardScreen } = await import("./setup/CentreSetupWizard");
    const { container } = render(wrap(<CentreSetupWizardScreen />));
    await expectNoSeriousAxe(container);
  });

  it("ExamEntryStatus empty+error surfaces", async () => {
    const { ExamEntryStatusBlock } = await import("./exams/ExamEntryStatus");
    const { container } = render(
      <ExamEntryStatusBlock error="load failed" loading={false} examCount={0} />
    );
    await expectNoSeriousAxe(container);
  });

  it("ExamAnalytics", async () => {
    const { ExamAnalyticsScreen } = await import("./exams/ExamAnalytics");
    const { container } = render(wrap(<ExamAnalyticsScreen />));
    await expectNoSeriousAxe(container);
  });

  it("VaultManagement", async () => {
    const { VaultManagementScreen } = await import("./vault/VaultManagement");
    const { container } = render(wrap(<VaultManagementScreen />));
    await expectNoSeriousAxe(container);
  });

  it("MessagingSettings", async () => {
    const { MessagingSettingsScreen } = await import("./settings/MessagingSettings");
    const { container } = render(wrap(<MessagingSettingsScreen />));
    await expectNoSeriousAxe(container);
  });

  it("ModeSettings", async () => {
    const { ModeSettingsScreen } = await import("./settings/ModeSettings");
    const { container } = render(wrap(<ModeSettingsScreen />));
    await expectNoSeriousAxe(container);
  });

  it("TodayAttendance", async () => {
    const { TodayAttendanceScreen } = await import("./attendance/TodayAttendance");
    const { container } = render(wrap(<TodayAttendanceScreen />));
    await expectNoSeriousAxe(container);
  });

  it("AttendanceHistory", async () => {
    const { AttendanceHistoryScreen } = await import("./attendance/AttendanceHistory");
    const { container } = render(wrap(<AttendanceHistoryScreen />));
    await expectNoSeriousAxe(container);
  });

  it("FeesThisMonth", async () => {
    const { FeesThisMonthScreen } = await import("./fees/FeesThisMonth");
    const { container } = render(wrap(<FeesThisMonthScreen />));
    await expectNoSeriousAxe(container);
  });

  it("GreenWhiteNagList", async () => {
    const { GreenWhiteNagListScreen } = await import("./fees/GreenWhiteNagList");
    const { container } = render(wrap(<GreenWhiteNagListScreen />));
    await expectNoSeriousAxe(container);
  });

  it("AdmissionsList", async () => {
    const { AdmissionsListScreen } = await import("./admissions/AdmissionsList");
    const { container } = render(wrap(<AdmissionsListScreen />));
    await expectNoSeriousAxe(container);
  });

  it("BatchSettings", async () => {
    const { BatchSettingsScreen } = await import("./batches/BatchSettings");
    const { container } = render(wrap(<BatchSettingsScreen />));
    await expectNoSeriousAxe(container);
  });
});
