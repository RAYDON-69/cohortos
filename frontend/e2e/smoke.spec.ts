/**
 * Full desk smoke: seed → login → Attendance → History → Admissions → Fees → Exams
 * → Vault → AI Copilot → Automations → Settings → Support.
 *
 * App uses HashRouter — all paths must be /#/...
 * CI starts with empty DBs — seed via /auth/centre-trial then session via
 * request-otp + verify-otp (COHORTOS_TEST_EXPOSE_OTP=1).
 */
import { test, expect } from "@playwright/test";
import path from "path";
import fs from "fs";

const API = process.env.COHORTOS_API_BASE || "http://127.0.0.1:8741";
const PHONE =
  process.env.COHORTOS_E2E_PHONE ||
  `0177${String(Date.now()).slice(-8)}`;

const shotDir = path.join("test-results", "smoke-shots");
fs.mkdirSync(shotDir, { recursive: true });

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
    /* page may be closed */
  }
}

test.describe.configure({ mode: "serial" });

test("desk smoke — login through support", async ({ page, request }) => {
  const health = await request.get(`${API}/health`).catch(() => null);
  if (!health || !health.ok()) {
    test.skip(true, `API not reachable at ${API}/health — start backend first`);
  }

  const trialRes = await request.post(`${API}/auth/centre-trial`, {
    data: {
      centre_name: `E2E Centre ${Date.now()}`,
      owner_phone: PHONE,
      owner_name: "E2E Owner",
      student_count: 1,
    },
  });
  const trialText = await trialRes.text();
  if (!trialRes.ok()) {
    throw new Error(`centre-trial failed ${trialRes.status()}: ${trialText}`);
  }
  const trial = JSON.parse(trialText);
  if (!trial.tenant_id) {
    throw new Error(`centre-trial missing tenant_id: ${trialText}`);
  }

  const otpRes = await request.post(`${API}/auth/request-otp`, {
    data: { phone: PHONE, tenant_id: trial.tenant_id },
  });
  const otpText = await otpRes.text();
  if (!otpRes.ok()) {
    throw new Error(`request-otp failed ${otpRes.status()}: ${otpText}`);
  }
  const otpBody = JSON.parse(otpText);
  if (!otpBody.otp_id) {
    throw new Error(`request-otp missing otp_id: ${otpText}`);
  }
  const code = String(otpBody._test_code || "");
  if (!code) {
    throw new Error(
      `request-otp missing _test_code (set COHORTOS_TEST_EXPOSE_OTP=1): ${otpText}`
    );
  }

  const verifyRes = await request.post(`${API}/auth/verify-otp`, {
    data: {
      phone: PHONE,
      code,
      otp_id: otpBody.otp_id,
      tenant_id: trial.tenant_id,
    },
  });
  const verifyText = await verifyRes.text();
  if (!verifyRes.ok()) {
    throw new Error(`verify-otp failed ${verifyRes.status()}: ${verifyText}`);
  }
  const session = JSON.parse(verifyText);
  if (!session.access_token || !session.refresh_token) {
    throw new Error(`verify-otp missing tokens: ${verifyText}`);
  }

  await page.goto(h("/login"));
  await shot(page, "01-login");
  await expect(page.getByText(/CohortOS|Welcome back|sign in/i).first()).toBeVisible({
    timeout: 15000,
  });

  // Hydrate SPA session via public E2E hooks (memory access + persisted refresh)
  await page.evaluate(
    ({ access, refresh, tenant, account }) => {
      localStorage.setItem("cohortos_refresh_token", refresh);
      localStorage.setItem("cohortos_tenant_id", tenant);
      localStorage.setItem("cohortos_account_id", account);
      const save = (window as unknown as { __COHORTOS_SAVE_TOKENS__?: (t: unknown) => void })
        .__COHORTOS_SAVE_TOKENS__;
      if (typeof save === "function") {
        save({
          access_token: access,
          refresh_token: refresh,
          tenant_id: tenant,
          account_id: account,
        });
      }
    },
    {
      access: session.access_token,
      refresh: session.refresh_token,
      tenant: String(session.tenant_id || trial.tenant_id),
      account: String(session.account_id || ""),
    }
  );
  await shot(page, "03-post-login");

  await page.goto(h("/attendance"));
  await page.waitForTimeout(1500);
  await shot(page, "04-attendance");
  if (await page.getByText(/Session required/i).count()) {
    throw new Error("Login did not establish session after token hydrate");
  }
  await expect(page.getByText(/Attendance|Present|Absent|Batch|Today/i).first()).toBeVisible({
    timeout: 15000,
  });
  await expect(page.getByText("Missing bearer token")).toHaveCount(0);

  await page.goto(h("/attendance/history"));
  await page.waitForTimeout(800);
  await shot(page, "05-history");
  await expect(page.getByText("Missing bearer token")).toHaveCount(0);
  await expect(page.getByText("No centre selected")).toHaveCount(0);

  await page.goto(h("/admissions"));
  await shot(page, "06-admissions");
  await expect(page.getByText(/Admit|Admissions|Name|Student/i).first()).toBeVisible({
    timeout: 10000,
  });
  await expect(page.getByText("Missing bearer token")).toHaveCount(0);

  await page.goto(h("/fees"));
  await page.waitForTimeout(800);
  await shot(page, "07-fees");
  await expect(page.getByText("Missing bearer token")).toHaveCount(0);
  await expect(page.getByText("No centre selected")).toHaveCount(0);

  await page.goto(h("/exams"));
  await page.waitForTimeout(800);
  await shot(page, "08-exams");
  await expect(page.getByText("Missing bearer token")).toHaveCount(0);
  await expect(page.getByText(/type.*loc.*msg.*input/i)).toHaveCount(0);

  await page.goto(h("/vault"));
  await page.waitForTimeout(800);
  await shot(page, "09-vault");
  await expect(page.getByText("Missing bearer token")).toHaveCount(0);

  await page.goto(h("/ai"));
  await page.waitForTimeout(800);
  await shot(page, "10-ai-copilot");
  await expect(page.getByText("Missing bearer token")).toHaveCount(0);

  await page.goto(h("/settings/automations"));
  await page.waitForTimeout(800);
  await shot(page, "11-automations");
  await expect(page.getByText("Missing bearer token")).toHaveCount(0);
  await expect(
    page.getByText(/Trigger|Condition|Action|Automations|Fee/i).first()
  ).toBeVisible({ timeout: 10000 });

  await page.goto(h("/settings"));
  await shot(page, "12-settings");
  await expect(page.getByText(/Settings|Integrations|Support|Staff/i).first()).toBeVisible({
    timeout: 10000,
  });

  await page.goto(h("/support"));
  await shot(page, "13-support");
  await expect(page.getByText(/Support|Contact|About/i).first()).toBeVisible({ timeout: 10000 });
  await expect(page.getByText("support@cohortos.app")).toBeVisible();
});
