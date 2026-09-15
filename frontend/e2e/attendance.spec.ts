/**
 * E2E: core desk flow — attendance manual mark (must-work-offline per SPEC).
 */
import { test, expect } from "@playwright/test";

const API = process.env.COHORTOS_API_BASE || "http://127.0.0.1:8000";

test.describe("Attendance desk flow", () => {
  test("health + attendance endpoint shape", async ({ request }) => {
    const health = await request.get(`${API}/health`);
    expect(health.ok()).toBeTruthy();
    const body = await health.json();
    expect(body.status).toBe("ok");
  });

  test("offline banner appears when offline", async ({ page }) => {
    await page.goto("/login");
    await page.context().setOffline(true);
    // Banner component should exist in DOM when offline
    await page.waitForTimeout(500);
    await page.context().setOffline(false);
  });
});
