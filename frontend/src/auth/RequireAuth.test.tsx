import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { RequireAuth } from "./RequireAuth";

vi.mock("../api/client", () => ({
  ensureSession: vi.fn(async () => false),
}));
vi.mock("../hooks/useLicenseLockout", () => ({
  useLicenseLockout: () => ({ locked: false, reason: null, loading: false, refresh: async () => {} }),
}));
vi.mock("../components/LicenseLockoutBanner", () => ({
  LicenseLockoutBanner: () => null,
}));

describe("RequireAuth", () => {
  it("renders recoverable sign-in when unauthenticated (never blank)", async () => {
    render(
      <MemoryRouter>
        <RequireAuth>
          <div>secret</div>
        </RequireAuth>
      </MemoryRouter>
    );
    await waitFor(() =>
      expect(screen.getByTestId("auth-required")).toBeInTheDocument()
    );
    expect(screen.getByText(/Back to sign in/i)).toBeInTheDocument();
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
  });
});
