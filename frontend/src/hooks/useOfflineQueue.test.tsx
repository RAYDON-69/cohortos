import { describe, it, expect } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useOfflineQueue } from "./useOfflineQueue";

describe("useOfflineQueue", () => {
  it("defaults to depth 0 without electron bridge", async () => {
    const { result } = renderHook(() => useOfflineQueue());
    await waitFor(() => expect(result.current.depth).toBe(0));
    expect(result.current.hasQueued).toBe(false);
  });
});
