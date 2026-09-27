/**
 * Full desk smoke: login → Attendance → History → Admissions → Fees → Exams
 * → Vault → AI Copilot → Automations → Settings → Support.
 * Screenshots every step. Video on failure (playwright config).
 *
 * App uses HashRouter — all paths must be /#/... not /...
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
/** Unique per run so CI empty DBs and retries never collide. */
const PHONE =
  process.env.COHORTOS_E2E_PHONE ||
  `0177${String(Date.now()).slice(-8)}`;

const shotDir = path.join("test-results", "smoke-shots");
fs.mkdirSync(shotDir, { recursive: true });
fs.mkdirSync(path.join("test-results"), { recursive: true });

/** HashRouter paths — never use bare /login (lands on * → /attendance → Session required). */
function h(route: string): string {
  const p = route.startsWith("/") ? route : `/${route}`;
  return `/#${p}`;
}

async function shot(page: import("@playwright/test").Page, name: string) {
  try {
    await page.screenshot({
      path: path.join(shotDir, `${name}.png`),
      fullPage: true,
    });
  } catch {
    /* page may be closed on hard crash */
  }
}

test.describe.configure({ mode: "serial" });

test("desk smoke — login through support", async ({ page, request }) => {
  // 0. API health
  const health = await request.get(`${API}/health`).catch(() => null);
  if (!health || !health.ok()) {
    test.skip(true, `API not reachable at ${API}/health — start backend first`);
  }

  // 0b. Seed a centre + owner on the empty CI DB. request-otp returns otp_id:null
  // for unknown phones ("If this phone is registered…") so OTP UI never appears.
  const trialRes = await request.post(`${API}/auth/centre-trial`, {
    data: {
      centre_name: `E2E Centre ${Date.now()}`,
      owner_phone: PHONE,
      owner_name: "E2E Owner",
      student_count: 1,
    },
  });
  if (!trialRes.ok()) {
    const body = await trialRes.text();
    throw new Error(`centre-trial failed ${trialRes.status()}: ${body}`);
  }
  const trial = await trialRes.json();
  if (!trial.tenant_id) {
    throw new Error(`centre-trial missing tenant_id: ${JSON.stringify(trial)}`);
  }

  // 1. Login — screenshot immediately so early failures still leave an artifact
  await page.goto(h("/login"));
  await shot(page, "01-login");
  await expect(page.getByText(/CohortOS|Welcome back|sign in/i).first()).toBeVisible({
    timeout: 15000,
  });

  // StaffLogin uses <label htmlFor="staff-phone"> + <Input id="staff-phone" type="tel">
  const phoneInput = page
    .locator("#staff-phone")
    .or(page.getByLabel(/^Phone$/i))
    .or(page.locator('input[type="tel"]'))
    .first();
  await expect(phoneInput).toBeVisible({ timeout: 10000 });
  await phoneInput.fill(PHONE);
  await page.getByRole("button", { name: /Send login code|Request OTP|OTP/i }).click();

  // Wait for OTP step (pilot exposes code in banner when COHORTOS_TEST_EXPOSE_OTP=1)
  await expect(page.locator("#staff-otp").or(page.getByText(/login code is|6-digit/i))).toBeVisible({
    timeout: 15000,
  });
  await shot(page, "02-otp");

  // Prefer pilot banner code; API also returns _test_code when expose flag is set
  const banner = page.locator("text=/login code is \\d+/i");
  let code = "";
  if (await banner.count()) {
    const txt = await banner.first().textContent();
    const m = txt?.match(/(\d{6})/);
    if (m) code = m[1];
  }
  if (!code) {
    // Fallback: request OTP via API with expose flag and read _test_code
    const otpApi = await request.post(`${API}/auth/request-otp`, {
      data: { phone: PHONE, tenant_id: trial.tenant_id },
    });
    const otpBody = await otpApi.json();
    code = String(otpBody._test_code || "");
  }
  if (!code) {
    throw new Error(
      "No OTP code available — set COHORTOS_TEST_EXPOSE_OTP=1 on the API (CI workflow should)."
    );
  }

  const codeInput = page
    .locator("#staff-otp")
    .or(page.getByLabel(/6-digit code|code/i))
    .or(page.locator('input[inputmode="numeric"]'))
    .first();
  await expect(codeInput).toBeVisible({ timeout: 10000 });
  await codeInput.fill(code);
  await page.getByRole("button", { name: /Sign in|Verify|Continue/i }).click();

  // Land on attendance or session required
  await page.waitForTimeout(2000);
  await shot(page, "03-post-login");

  if (await page.getByText(/Session required/i).count()) {
    throw new Error("Login did not establish session — refresh/OTP path broken");
  }

  // 2. Attendance
  await page.goto(h("/attendance"));
  await shot(page, "04-attendance");
  await expect(page.getByText(/Attendance|Present|Absent|Batch/i).first()).toBeVisible({
    timeout: 15000,
  });
  const presentBtn = page.getByRole("button", { name: /^Present$/i }).first();
  if (await presentBtn.count()) {
    await presentBtn.click();
    await page.waitForTimeout(400);
  }

  // 3. History (App route is /attendance/history)
  await page.goto(h("/attendance/history"));
  await page.waitForTimeout(800);
  await shot(page, "05-history");
  await expect(page.getByText("Missing bearer token")).toHaveCount(0);
  await expect(page.getByText("No centre selected")).toHaveCount(0);

  // 4. Admissions
  await page.goto(h("/admissions"));
  await shot(page, "06-admissions");
  await expect(page.getByText(/Admit|Admissions|Name/i).first()).toBeVisible({ timeout: 10000 });
  await expect(page.getByText("Missing bearer token")).toHaveCount(0);

  // 5. Fees
  await page.goto(h("/fees"));
  await page.waitForTimeout(800);
  await shot(page, "07-fees");
  await expect(page.getByText("Missing bearer token")).toHaveCount(0);
  await expect(page.getByText("No centre selected")).toHaveCount(0);

  // 6. Exams
  await page.goto(h("/exams"));
  await page.waitForTimeout(800);
  await shot(page, "08-exams");
  await expect(page.getByText("Missing bearer token")).toHaveCount(0);
  await expect(page.getByText(/type.*loc.*msg.*input/i)).toHaveCount(0);

  // 7. Vault
  await page.goto(h("/vault"));
  await page.waitForTimeout(800);
  await shot(page, "09-vault");
  await expect(page.getByText("Missing bearer token")).toHaveCount(0);

  // 8. AI Copilot
  await page.goto(h("/ai"));
  await page.waitForTimeout(800);
  await shot(page, "10-ai-copilot");
  await expect(page.getByText("Missing bearer token")).toHaveCount(0);

  // 9. Automations
  await page.goto(h("/settings/automations"));
  await page.waitForTimeout(800);
  await shot(page, "11-automations");
  await expect(page.getByText("Missing bearer token")).toHaveCount(0);

  // 10. Settings hub
  await page.goto(h("/settings"));
  await shot(page, "12-settings");
  await expect(page.getByText(/Settings|Integrations|Support/i).first()).toBeVisible({
    timeout: 10000,
  });

  // 11. Support / Legal
  await page.goto(h("/support"));
  await shot(page, "13-support");
  await expect(page.getByText(/Support|Contact|About/i).first()).toBeVisible({ timeout: 10000 });
  await expect(page.getByText("support@cohortos.app")).toBeVisible();
});
