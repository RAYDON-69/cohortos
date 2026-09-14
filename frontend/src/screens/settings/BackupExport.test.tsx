import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { BackupExportScreen } from "./BackupExport";

vi.mock("../../hooks/useTenant", () => ({
  useTenant: () => ({ tenantId: "t-1" }),
}));
vi.mock("../../hooks/useLicenseLockout", () => ({
  useLicenseLockout: () => ({ locked: false, reason: null, loading: false, refresh: async () => {} }),
}));
vi.mock("../../api/client", () => ({
  getBackupStatus: vi.fn(),
  triggerBackupExport: vi.fn(),
}));
vi.mock("../../shell/AppShell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock("../../nav/deskNav", () => ({
  buildDeskNav: () => [],
}));

describe("BackupExportScreen", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows WAL status on success", async () => {
    const { getBackupStatus } = await import("../../api/client");
    (getBackupStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      db_path: ":memory:",
      wal_active: false,
      journal_mode: "memory",
      backups: [],
      backup_dir: null,
    });
    render(
      <MemoryRouter>
        <BackupExportScreen />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText(/Database durability/i)).toBeInTheDocument());
    expect(screen.getByText(/Journal mode:/i)).toBeInTheDocument();
    expect(screen.getByText(/WAL active:/i)).toBeInTheDocument();
    expect(screen.getByText(/Export full dataset/i)).toBeInTheDocument();
  });

  it("error state with retry", async () => {
    const { getBackupStatus } = await import("../../api/client");
    (getBackupStatus as ReturnType<typeof vi.fn>).mockRejectedValue({ detail: "backup offline" });
    render(
      <MemoryRouter>
        <BackupExportScreen />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/backup offline/i));
    expect(screen.getByText(/Retry/i)).toBeInTheDocument();
  });
});
