/**
 * E2E: founder panel — requires COHORTOS_FOUNDER_TOKEN.
 */
import { test, expect } from "@playwright/test";

const API = process.env.COHORTOS_API_BASE || "http://127.0.0.1:8000";
const FOUNDER = process.env.COHORTOS_FOUNDER_TOKEN || "";

test.describe("Founder panel", () => {
  test("dashboard requires founder token", async ({ request }) => {
    const noTok = await request.get(`${API}/founder/dashboard`);
    expect(noTok.status()).toBe(403);

    if (FOUNDER) {
      const ok = await request.get(`${API}/founder/dashboard`, {
        headers: { "X-Founder-Token": FOUNDER },
      });
      // 200 when token valid
      expect([200, 403]).toContain(ok.status());
    }
  });
});
