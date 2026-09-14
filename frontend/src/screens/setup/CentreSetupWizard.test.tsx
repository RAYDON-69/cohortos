import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { CentreSetupWizardScreen } from "./CentreSetupWizard";

vi.mock("../../hooks/useTenant", () => ({
  useTenant: () => ({ tenantId: "t-1" }),
}));
vi.mock("../../hooks/useConnectivity", () => ({
  useConnectivity: () => ({
    state: "synced",
    isOffline: false,
    isSyncing: false,
    isSynced: true,
    hasConflict: false,
  }),
}));
vi.mock("../../api/client", () => ({
  getSetupStatus: vi.fn(),
  setupFirstBatch: vi.fn(),
  admitStudent: vi.fn(),
  listBatches: vi.fn(),
}));

describe("CentreSetupWizardScreen", () => {
  beforeEach(() => vi.clearAllMocks());

  it("empty state when no batches yet", async () => {
    const api = await import("../../api/client");
    (api.getSetupStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      needs_wizard: true,
      batch_count: 0,
      student_count: 0,
      steps: { centre: true, first_batch: false, first_admission: false, done: false },
    });
    render(
      <MemoryRouter>
        <CentreSetupWizardScreen />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText(/No batches yet/i)).toBeInTheDocument());
    expect(screen.getByTestId("setup-empty-batch")).toBeInTheDocument();
  });

  it("error state with retry", async () => {
    const api = await import("../../api/client");
    (api.getSetupStatus as ReturnType<typeof vi.fn>).mockRejectedValue({
      detail: "setup status failed",
    });
    render(
      <MemoryRouter>
        <CentreSetupWizardScreen />
      </MemoryRouter>
    );
    await waitFor(() =>
      expect(screen.getByTestId("setup-error")).toHaveTextContent(/setup status failed/i)
    );
    expect(screen.getByText(/Retry/i)).toBeInTheDocument();
  });
});
