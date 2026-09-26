/**
 * Full desk smoke: login → Attendance → History → Admissions → Fees → Exams
 * → Vault → AI Copilot → Automations → Settings → Support.
 * Screenshots every step. Video on failure (playwright config).
 *
 * Requires:
 * - API at COHORTOS_API_BASE (default http://127.0.0.1:8741)
 * - Frontend at baseURL (default http://127.0.0.1:5173)
 * - Pilot OTP mode (API returns _test_code or pilot banner shows code)
 */
import { test, expect } from "@playwright/test";
import path from "path";
import fs from "fs";

const API = process.env.COHORTOS_API_BASE || "http://127.0.0.1:8741";
const PHONE = process.env.COHORTOS_E2E_PHONE || "01774656829";

const shotDir = path.join("test-results", "smoke-shots");
fs.mkdirSync(shotDir, { recursive: true });

async function shot(page: import("@playwright/test").Page, name: string) {
  await page.screenshot({
    path: path.join(shotDir, `${name}.png`),
    fullPage: true,
  });
}

test.describe.configure({ mode: "serial" });

test("desk smoke — login through support", async ({ page, request }) => {
  // 0. API health
  const health = await request.get(`${API}/health`).catch(() => null);
  if (!health || !health.ok()) {
    test.skip(true, `API not reachable at ${API}/health — start backend first`);
  }

  // 1. Login — screenshot immediately so early failures still leave an artifact
  await page.goto("/login");
  await shot(page, "01-login");
  await expect(page.getByText(/CohortOS|Welcome back|sign in/i).first()).toBeVisible({ timeout: 15000 });

  const phoneInput = page.getByLabel(/Phone/i).or(page.locator('input[type="tel"], input[placeholder*="01"]')).first();
  await phoneInput.fill(PHONE);
  await page.getByRole("button", { name: /Send login code|Request OTP|OTP/i }).click();

  // Pilot mode shows code in banner or input
  await page.waitForTimeout(800);
  await shot(page, "02-otp");

  // Prefer pilot banner code, else type a known pilot code pattern
  const banner = page.locator("text=/login code is \\d+/i");
  let code = "695094";
  if (await banner.count()) {
    const txt = await banner.first().textContent();
    const m = txt?.match(/(\d{6})/);
    if (m) code = m[1];
  }
  const codeInput = page.getByLabel(/code|6-digit/i).or(page.locator('input[inputmode="numeric"], input[maxlength="6"]')).first();
  await codeInput.fill(code);
  await page.getByRole("button", { name: /Sign in|Verify|Continue/i }).click();

  // Land on attendance or session required
  await page.waitForTimeout(1500);
  await shot(page, "03-post-login");

  // If session required, fail clearly
  if (await page.getByText(/Session required/i).count()) {
    throw new Error("Login did not establish session — refresh/OTP path broken");
  }

  // 2. Attendance
  await page.goto("/attendance");
  await shot(page, "04-attendance");
  await expect(page.getByText(/Attendance|Present|Absent|Batch/i).first()).toBeVisible({ timeout: 15000 });
  // Try mark Present if buttons exist
  const presentBtn = page.getByRole("button", { name: /^Present$/i }).first();
  if (await presentBtn.count()) {
    await presentBtn.click();
    await page.waitForTimeout(400);
  }

  // 3. History
  await page.goto("/history");
  await page.waitForTimeout(800);
  await shot(page, "05-history");
  // Must not show raw "Missing bearer token"
  await expect(page.getByText("Missing bearer token")).toHaveCount(0);
  await expect(page.getByText("No centre selected")).toHaveCount(0);

  // 4. Admissions
  await page.goto("/admissions");
  await expect(page.getByText(/Admit|Admissions|Name/i).first()).toBeVisible({ timeout: 10000 });
  await shot(page, "06-admissions");
  await expect(page.getByText("Missing bearer token")).toHaveCount(0);

  // 5. Fees
  await page.goto("/fees");
  await page.waitForTimeout(800);
  await shot(page, "07-fees");
  await expect(page.getByText("Missing bearer token")).toHaveCount(0);
  await expect(page.getByText("No centre selected")).toHaveCount(0);

  // 6. Exams
  await page.goto("/exams");
  await page.waitForTimeout(800);
  await shot(page, "08-exams");
  await expect(page.getByText("Missing bearer token")).toHaveCount(0);
  // Must not crash with React #31 / raw validation object
  await expect(page.getByText(/type.*loc.*msg.*input/i)).toHaveCount(0);

  // 7. Vault
  await page.goto("/vault");
  await page.waitForTimeout(800);
  await shot(page, "09-vault");
  await expect(page.getByText("Missing bearer token")).toHaveCount(0);

  // 8. AI Copilot
  await page.goto("/ai");
  await page.waitForTimeout(800);
  await shot(page, "10-ai-copilot");
  await expect(page.getByText("Missing bearer token")).toHaveCount(0);

  // 9. Automations
  await page.goto("/settings/automations");
  await page.waitForTimeout(800);
  await shot(page, "11-automations");
  await expect(page.getByText("Missing bearer token")).toHaveCount(0);

  // 10. Settings hub
  await page.goto("/settings");
  await expect(page.getByText(/Settings|Integrations|Support/i).first()).toBeVisible({ timeout: 10000 });
  await shot(page, "12-settings");

  // 11. Support / Legal
  await page.goto("/support");
  await expect(page.getByText(/Support|Contact|About/i).first()).toBeVisible({ timeout: 10000 });
  await shot(page, "13-support");
  await expect(page.getByText("support@cohortos.app")).toBeVisible();
});
