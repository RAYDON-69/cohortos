/**
 * Batch 5 a11y smoke — LicenseLockout, Badge (not color-only), EmptyState.
 */
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { axe } from "vitest-axe";
import { LicenseLockoutBanner } from "./LicenseLockoutBanner";
import { AttendanceBadge, PaymentBadge } from "./Badge";
import { EmptyState } from "./EmptyState";
import { Button } from "./Button";

describe("Batch 5 a11y", () => {
  it("LicenseLockoutBanner is an alert with no serious axe issues", async () => {
    const { container, getByRole } = render(<LicenseLockoutBanner reason="Past grace" />);
    expect(getByRole("alert")).toBeTruthy();
    const results = await axe(container);
    expect(results.violations.filter((v) => v.impact === "critical" || v.impact === "serious")).toEqual([]);
  });

  it("AttendanceBadge exposes status role with text (not color alone)", () => {
    const { getByRole } = render(<AttendanceBadge status="absent" />);
    expect(getByRole("status").textContent).toMatch(/Absent/i);
  });

  it("PaymentBadge locked has text label", () => {
    const { getByRole } = render(<PaymentBadge status="locked" />);
    expect(getByRole("status").textContent).toMatch(/Locked/i);
  });

  it("EmptyState + Button action is accessible", async () => {
    const { container } = render(
      <EmptyState title="Nothing here" body="Add a row" action={<Button>Add</Button>} />
    );
    const results = await axe(container);
    expect(results.violations.filter((v) => v.impact === "critical" || v.impact === "serious")).toEqual([]);
  });
});
