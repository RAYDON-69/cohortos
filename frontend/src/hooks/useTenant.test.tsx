import { describe, it, expect, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { useTenant } from "./useTenant";

vi.mock("../api/client", () => ({
  loadTokens: vi.fn(() => ({ tenant_id: "t-1", account_id: "a-1" })),
}));

describe("useTenant", () => {
  it("returns tenantId from tokens", () => {
    const { result } = renderHook(() => useTenant());
    expect(result.current.tenantId).toBe("t-1");
  });

  it("empty state when no tenant", async () => {
    const { loadTokens } = await import("../api/client");
    (loadTokens as ReturnType<typeof vi.fn>).mockReturnValueOnce({});
    const { result } = renderHook(() => useTenant());
    expect(result.current.tenantId).toBe("");
  });
});
