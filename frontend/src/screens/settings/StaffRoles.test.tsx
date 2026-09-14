import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { StaffRolesScreen } from "./StaffRoles";

vi.mock("../../i18n/LocaleContext", () => ({
  useLocale: () => ({ t: (k: string) => k, locale: "en" }),
}));
vi.mock("../../shell/AppShell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock("../../nav/deskNav", () => ({ buildDeskNav: () => [] }));
vi.mock("../../api/client", () => ({
  loadTokens: () => ({ tenant_id: "t-1" }),
  listStaff: vi.fn(),
  createStaff: vi.fn(),
  assignStaffRole: vi.fn(),
}));

describe("StaffRolesScreen", () => {
  beforeEach(() => vi.clearAllMocks());

  it("empty state when no staff", async () => {
    const api = await import("../../api/client");
    (api.listStaff as ReturnType<typeof vi.fn>).mockResolvedValue({ staff: [], roles: [] });
    render(
      <MemoryRouter>
        <StaffRolesScreen />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText(/No staff yet/i)).toBeInTheDocument());
  });

  it("error state", async () => {
    const api = await import("../../api/client");
    (api.listStaff as ReturnType<typeof vi.fn>).mockRejectedValue({ detail: "staff list failed" });
    render(
      <MemoryRouter>
        <StaffRolesScreen />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText(/staff list failed/i)).toBeInTheDocument());
  });
});
