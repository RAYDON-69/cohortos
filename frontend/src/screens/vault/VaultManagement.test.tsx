import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { VaultManagementScreen } from "./VaultManagement";

vi.mock("../../i18n/LocaleContext", () => ({
  useLocale: () => ({ t: (k: string) => k, locale: "en" }),
}));
vi.mock("../../shell/AppShell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock("../../nav/deskNav", () => ({ buildDeskNav: () => [] }));
vi.mock("../../api/client", () => ({
  loadTokens: () => ({ tenant_id: "t-1" }),
  listVault: vi.fn(),
  listBatches: vi.fn(),
  createVaultResource: vi.fn(),
  setVaultAccessRules: vi.fn(),
  relaxVaultProtection: vi.fn(),
  restoreVaultProtection: vi.fn(),
}));

describe("VaultManagementScreen", () => {
  beforeEach(() => vi.clearAllMocks());

  it("empty state when no resources", async () => {
    const api = await import("../../api/client");
    (api.listVault as ReturnType<typeof vi.fn>).mockResolvedValue({ resources: [] });
    (api.listBatches as ReturnType<typeof vi.fn>).mockResolvedValue({ batches: [] });
    render(
      <MemoryRouter>
        <VaultManagementScreen />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText(/No resources yet/i)).toBeInTheDocument());
  });

  it("error state", async () => {
    const api = await import("../../api/client");
    (api.listVault as ReturnType<typeof vi.fn>).mockRejectedValue({ detail: "vault unavailable" });
    (api.listBatches as ReturnType<typeof vi.fn>).mockResolvedValue({ batches: [] });
    render(
      <MemoryRouter>
        <VaultManagementScreen />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText(/vault unavailable/i)).toBeInTheDocument());
  });
});
