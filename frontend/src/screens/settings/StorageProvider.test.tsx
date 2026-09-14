import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { StorageProviderScreen } from "./StorageProvider";

vi.mock("../../hooks/useTenant", () => ({
  useTenant: () => ({ tenantId: "t-1" }),
}));
vi.mock("../../shell/AppShell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock("../../nav/deskNav", () => ({ buildDeskNav: () => [] }));
vi.mock("../../api/client", () => ({
  getStorageSettings: vi.fn(),
  putStorageSettings: vi.fn(),
  testStorageProvider: vi.fn(),
}));

describe("StorageProviderScreen", () => {
  beforeEach(() => vi.clearAllMocks());

  it("not configured empty CTA for google drive", async () => {
    const api = await import("../../api/client");
    (api.getStorageSettings as ReturnType<typeof vi.fn>).mockResolvedValue({
      provider: "google_drive",
      configured: false,
      options: ["google_drive", "local_fs"],
    });
    render(
      <MemoryRouter>
        <StorageProviderScreen />
      </MemoryRouter>
    );
    await waitFor(() =>
      expect(screen.getByText(/Google Drive not connected/i)).toBeInTheDocument()
    );
  });

  it("error state with retry", async () => {
    const api = await import("../../api/client");
    (api.getStorageSettings as ReturnType<typeof vi.fn>).mockRejectedValue({
      detail: "storage settings failed",
    });
    render(
      <MemoryRouter>
        <StorageProviderScreen />
      </MemoryRouter>
    );
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/storage settings failed/i)
    );
    expect(screen.getByText(/Retry/i)).toBeInTheDocument();
  });
});
