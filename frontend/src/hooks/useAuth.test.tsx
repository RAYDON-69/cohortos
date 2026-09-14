import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useAuth } from "./useAuth";

vi.mock("../api/client", () => ({
  loadTokens: vi.fn(() => ({})),
  saveTokens: vi.fn(),
  clearTokens: vi.fn(),
  ensureSession: vi.fn(async () => false),
  requestOtp: vi.fn(),
  verifyOtp: vi.fn(),
}));

describe("useAuth", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("starts unauthenticated when no tokens", async () => {
    const { result } = renderHook(() => useAuth());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.isAuthenticated).toBe(false);
  });

  it("exposes logout that clears session", async () => {
    const { clearTokens } = await import("../api/client");
    const { result } = renderHook(() => useAuth());
    await waitFor(() => expect(result.current.loading).toBe(false));
    await result.current.logout();
    expect(clearTokens).toHaveBeenCalled();
  });
});
