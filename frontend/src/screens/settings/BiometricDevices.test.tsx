import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { BiometricDevicesScreen } from "./BiometricDevices";

vi.mock("../../hooks/useTenant", () => ({
  useTenant: () => ({ tenantId: "t-1" }),
}));
vi.mock("../../shell/AppShell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock("../../nav/deskNav", () => ({ buildDeskNav: () => [] }));
vi.mock("../../api/client", () => ({
  getBiometricStatus: vi.fn(),
  registerBiometricDevice: vi.fn(),
  testBiometricDevice: vi.fn(),
  disableBiometricDevice: vi.fn(),
  linkDeviceUser: vi.fn(),
  linkDeviceUserBulk: vi.fn(),
  apiRequest: vi.fn(),
  tenantPath: (t: string, s: string) => `/t/${t}${s}`,
}));

describe("BiometricDevicesScreen", () => {
  beforeEach(() => vi.clearAllMocks());

  it("empty state when no devices", async () => {
    const api = await import("../../api/client");
    (api.getBiometricStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      pyzk_available: true,
      devices: [],
    });
    render(
      <MemoryRouter>
        <BiometricDevicesScreen />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText(/No devices/i)).toBeInTheDocument());
  });

  it("error state with retry", async () => {
    const api = await import("../../api/client");
    (api.getBiometricStatus as ReturnType<typeof vi.fn>).mockRejectedValue({
      detail: "devices offline",
    });
    render(
      <MemoryRouter>
        <BiometricDevicesScreen />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/devices offline/i));
    expect(screen.getByText(/Retry/i)).toBeInTheDocument();
  });

  it("shows library missing banner when pyzk false", async () => {
    const api = await import("../../api/client");
    (api.getBiometricStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      pyzk_available: false,
      devices: [],
    });
    render(
      <MemoryRouter>
        <BiometricDevicesScreen />
      </MemoryRouter>
    );
    await waitFor(() =>
      expect(screen.getByTestId("pyzk-missing")).toHaveTextContent(/Biometric library not installed/i)
    );
  });
});
