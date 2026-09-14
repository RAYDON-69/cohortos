/**
 * a11y smoke — Portion 24
 * Offline banner must expose role=status and not rely on color alone.
 */
import React from "react";
import { describe, it, expect, beforeEach } from "vitest";
import { render } from "@testing-library/react";
import { axe } from "vitest-axe";
import { OfflineBanner } from "./OfflineBanner";
import { setSyncState } from "../api/client";
import { LocaleProvider } from "../i18n/LocaleContext";

function wrap(ui: React.ReactNode) {
  return <LocaleProvider>{ui}</LocaleProvider>;
}

describe("OfflineBanner a11y", () => {
  beforeEach(() => {
    setSyncState("offline");
  });

  it("has no axe violations when offline", async () => {
    const { container } = render(wrap(<OfflineBanner />));
    const results = await axe(container);
    expect(results.violations).toEqual([]);
  });

  it("announces offline with role=status", () => {
    const { getByRole } = render(wrap(<OfflineBanner />));
    expect(getByRole("status")).toBeTruthy();
  });
});
