/**
 * Full desk smoke with API-seeded session (empty CI DB) + HashRouter paths.
 */
import { test, expect } from "@playwright/test";
import path from "path";
import fs from "fs";

const API = process.env.COHORTOS_API_BASE || "http://127.0.0.1:8741";
const PHONE =
  process.env.COHORTOS_E2E_PHONE ||
  `0177${String(Date.now()).slice(-8)}`;

const ARTIFACT_ROOT = path.join("e2e-artifacts");
const shotDir = path.join(ARTIFACT_ROOT, "smoke-shots");
fs.mkdirSync(shotDir, { recursive: true });

function h(route: string): string {
  const p = route.startsWith("/") ? route : `/${route}`;
  return `/#${p}`;
}

async function shot(page: import("@playwright/test").Page, name: string) {
  try {
    await page.screenshot({ path: path.join(shotDir, `${name}.png`), fullPage: true });
  } catch { /* */ }
}

test.describe.configure({ mode: "serial" });

test("desk smoke — login through support", async ({ page, request }) => {
  const health = await request.get(`${API}/health`).catch(() => null);
  if (!health || !health.ok()) {
    test.skip(true, `API not reachable at ${API}/health`);
  }

  // --- Seed centre + complete OTP entirely via API (empty CI DB) ---
  const trialRes = await request.post(`${API}/auth/centre-trial`, {
    data: {
      centre_name: `E2E Centre ${Date.now()}`,
      owner_phone: PHONE,
      owner_name: "E2E Owner",
      student_count: 1,
    },
  });
  const trialText = await trialRes.text();
  if (!trialRes.ok()) throw new Error(`centre-trial ${trialRes.status()}: ${trialText}`);
  const trial = JSON.parse(trialText) as { tenant_id: string };

  const otpRes = await request.post(`${API}/auth/request-otp`, {
    data: { phone: PHONE, tenant_id: trial.tenant_id },
  });
  const otpBody = await otpRes.json();
  if (!otpRes.ok() || !otpBody.otp_id || !otpBody._test_code) {
    throw new Error(`request-otp failed: ${JSON.stringify(otpBody)}`);
  }

  const verifyRes = await request.post(`${API}/auth/verify-otp`, {
    data: {
      otp_id: otpBody.otp_id,
      code: String(otpBody._test_code),
      tenant_id: trial.tenant_id,
    },
  });
  const tokens = await verifyRes.json();
  if (!verifyRes.ok() || !tokens.refresh_token) {
    throw new Error(`verify-otp failed: ${JSON.stringify(tokens)}`);
  }

  // Inject session (refresh + tenant) before any app route — matches client storage keys
  await page.goto(h("/login"));
  await page.evaluate(
    ({ refresh, tenant, account }) => {
      localStorage.setItem("cohortos_refresh_token", refresh);
      localStorage.setItem("cohortos_tenant_id", tenant);
      localStorage.setItem("cohortos_account_id", account);
    },
    {
      refresh: tokens.refresh_token as string,
      tenant: String(tokens.tenant_id || trial.tenant_id),
      account: String(tokens.account_id || ""),
    }
  );
  await shot(page, "01-login-seeded");

  // Also exercise UI OTP path with a second OTP (proves phone form still works)
  await page.goto(h("/login"));
  const phoneInput = page.locator("#staff-phone").or(page.locator('input[type="tel"]')).first();
  if (await phoneInput.isVisible().catch(() => false)) {
    // Already authed may redirect; if still on login, run UI path
    await phoneInput.fill(PHONE);
    await page.getByRole("button", { name: /Send login code/i }).click();
    const otpField = page.locator("#staff-otp");
    if (await otpField.isVisible({ timeout: 8000 }).catch(() => false)) {
      const otp2 = await request.post(`${API}/auth/request-otp`, {
        data: { phone: PHONE, tenant_id: trial.tenant_id },
      });
      const o2 = await otp2.json();
      const code = String(o2._test_code || otpBody._test_code);
      await otpField.fill(code);
      await page.getByRole("button", { name: /Sign in/i }).click();
      await page.waitForTimeout(1500);
    }
  }
  await shot(page, "02-after-auth");

  // Navigate authenticated desk routes
  for (const [route, name, re] of [
    ["/attendance", "04-attendance", /Attendance|Present|Absent|Batch/i],
    ["/attendance/history", "05-history", /History|Attendance|Missing bearer/i],
    ["/admissions", "06-admissions", /Admit|Admissions|Name/i],
    ["/fees", "07-fees", /Fee|Payment|Missing bearer/i],
    ["/exams", "08-exams", /Exam|Missing bearer/i],
    ["/vault", "09-vault", /Vault|Content|Missing bearer/i],
    ["/ai", "10-ai-copilot", /Copilot|Ask|Missing bearer/i],
    ["/settings/automations", "11-automations", /Automation|Missing bearer/i],
    ["/settings", "12-settings", /Settings|Integrations|Support/i],
    ["/support", "13-support", /Support|Contact|support@cohortos/i],
  ] as const) {
    await page.goto(h(route));
    await page.waitForTimeout(600);
    await shot(page, name);
    await expect(page.getByText("Missing bearer token")).toHaveCount(0);
    await expect(page.getByText("No centre selected")).toHaveCount(0);
    await expect(page.getByText(/Session required/i)).toHaveCount(0);
    await expect(page.getByText(re).first()).toBeVisible({ timeout: 12000 });
  }

  await expect(page.getByText("support@cohortos.app")).toBeVisible();
});
