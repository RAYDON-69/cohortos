import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ConflictLogScreen } from "./ConflictLog";

vi.mock("../../hooks/useTenant", () => ({
  useTenant: () => ({ tenantId: "t-1" }),
}));
vi.mock("../../hooks/useLicenseLockout", () => ({
  useLicenseLockout: () => ({ locked: false, reason: null, loading: false, refresh: async () => {} }),
}));
vi.mock("../../api/client", () => ({
  listSyncConflicts: vi.fn(),
  resolveSyncConflict: vi.fn(),
}));
vi.mock("../../shell/AppShell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock("../../nav/deskNav", () => ({
  buildDeskNav: () => [],
}));

describe("ConflictLogScreen", () => {
  beforeEach(() => vi.clearAllMocks());

  it("empty state when no conflicts", async () => {
    const { listSyncConflicts } = await import("../../api/client");
    (listSyncConflicts as ReturnType<typeof vi.fn>).mockResolvedValue({ conflicts: [] });
    render(
      <MemoryRouter>
        <ConflictLogScreen />
      </MemoryRouter>
    );
    await waitFor(() =>
      expect(screen.getByText(/No open conflicts/i)).toBeInTheDocument()
    );
  });

  it("error state with retry", async () => {
    const { listSyncConflicts } = await import("../../api/client");
    (listSyncConflicts as ReturnType<typeof vi.fn>).mockRejectedValue({ detail: "network down" });
    render(
      <MemoryRouter>
        <ConflictLogScreen />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/network down/i));
    expect(screen.getByText(/Retry/i)).toBeInTheDocument();
  });
});
