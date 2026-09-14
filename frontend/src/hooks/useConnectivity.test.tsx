import { describe, it, expect, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { useConnectivity } from "./useConnectivity";

vi.mock("../api/client", () => ({
  getSyncState: vi.fn(() => "offline"),
  setSyncStateListener: vi.fn((fn: (s: string) => void) => fn("offline")),
  startConnectivityPoll: vi.fn(),
  stopConnectivityPoll: vi.fn(),
}));

describe("useConnectivity", () => {
  it("reports offline state", () => {
    const { result } = renderHook(() => useConnectivity());
    expect(result.current.isOffline).toBe(true);
  });
});
