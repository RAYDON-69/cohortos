import { describe, it, expect, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useApi } from "./useApi";

vi.mock("../api/client", () => ({
  apiRequest: vi.fn(),
}));

describe("useApi", () => {
  it("maps success", async () => {
    const { apiRequest } = await import("../api/client");
    (apiRequest as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ ok: true });
    const { result } = renderHook(() => useApi());
    await act(async () => {
      const data = await result.current.request("/x");
      expect(data).toEqual({ ok: true });
    });
    expect(result.current.error).toBeNull();
  });

  it("maps error to UI state", async () => {
    const { apiRequest } = await import("../api/client");
    (apiRequest as ReturnType<typeof vi.fn>).mockRejectedValueOnce({ detail: "boom" });
    const { result } = renderHook(() => useApi());
    await act(async () => {
      const data = await result.current.request("/x");
      expect(data).toBeNull();
    });
    expect(result.current.error).toBe("boom");
  });
});
