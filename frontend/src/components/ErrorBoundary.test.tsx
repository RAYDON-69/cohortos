import { describe, it, expect } from "vitest";
import { vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ErrorBoundary } from "./ErrorBoundary";

function Boom(): null {
  throw new Error("intentional crash");
}

describe("ErrorBoundary", () => {
  it("never leaves a blank screen — shows recovery UI", () => {
    // suppress expected error noise
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <MemoryRouter>
        <ErrorBoundary>
          <Boom />
        </ErrorBoundary>
      </MemoryRouter>
    );
    expect(screen.getByTestId("error-boundary")).toBeInTheDocument();
    expect(screen.getByText(/Back to attendance/i)).toBeInTheDocument();
    spy.mockRestore();
  });
});
