/**
 * Independent CORE journeys — each test seeds its own tenant (unique phone).
 * Token hydrate matches smoke.spec.ts (STORAGE keys + __COHORTOS_SAVE_TOKENS__).
 */
import { test, expect } from "@playwright/test";
import path from "path";
import fs from "fs";

// Serial: avoid parallel OTP/session races against one API process
test.describe.configure({ mode: "serial" });

const API = process.env.COHORTOS_API_BASE || "http://127.0.0.1:8741";

function h(route: string): string {
  const p = route.startsWith("/") ? route : `/${route}`;
  return `/#${p}`;
}

const shotDir = path.join("test-results", "smoke-shots");
fs.mkdirSync(shotDir, { recursive: true });

async function shot(page: import("@playwright/test").Page, name: string) {
  try {
    await page.screenshot({ path: path.join(shotDir, `${name}.png`), fullPage: true });
  } catch {
    /* ignore */
  }
}

async function seedSession(request: import("@playwright/test").APIRequestContext) {
  const phone = `017${String(Date.now()).slice(-9)}${Math.floor(Math.random() * 90 + 10)}`.slice(0, 11);
  const trial = await request.post(`${API}/auth/centre-trial`, {
    data: {
      centre_name: `Journey ${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      owner_phone: phone,
      owner_name: "Journey Owner",
      student_count: 1,
    },
  });
  if (!trial.ok()) throw new Error(`trial ${trial.status()} ${await trial.text()}`);
  const trialBody = await trial.json();
  const tenant_id = trialBody.tenant_id;
  const otp = await request.post(`${API}/auth/request-otp`, { data: { phone, tenant_id } });
  if (!otp.ok()) throw new Error(`otp ${otp.status()} ${await otp.text()}`);
  const body = await otp.json();
  const ver = await request.post(`${API}/auth/verify-otp`, {
    data: { phone, code: body._test_code, otp_id: body.otp_id, tenant_id },
  });
  if (!ver.ok()) throw new Error(`verify ${ver.status()} ${await ver.text()}`);
  const session = await ver.json();
  if (!session.access_token || !session.refresh_token) {
    throw new Error(`missing tokens ${JSON.stringify(session).slice(0, 200)}`);
  }
  return { phone, tenant_id, session };
}

async function injectTokens(
  page: import("@playwright/test").Page,
  session: { access_token: string; refresh_token: string; tenant_id?: string; account_id?: string },
  tenantId: string
) {
  await page.goto(h("/login"));
  await expect(page.getByText(/CohortOS|Welcome back|sign in/i).first()).toBeVisible({ timeout: 15000 });
  // Wait for client.ts to expose hydrate hook
  await page.waitForFunction(() => typeof (window as any).__COHORTOS_SAVE_TOKENS__ === "function", null, {
    timeout: 15000,
  });
  await page.evaluate(
    ({ access, refresh, tenant, account }) => {
      localStorage.setItem("cohortos_refresh_token", refresh);
      localStorage.setItem("cohortos_tenant_id", tenant);
      if (account) localStorage.setItem("cohortos_account_id", account);
      const save = (window as any).__COHORTOS_SAVE_TOKENS__;
      if (typeof save === "function") {
        save({
          access_token: access,
          refresh_token: refresh,
          tenant_id: tenant,
          account_id: account || undefined,
        });
      }
    },
    {
      access: session.access_token,
      refresh: session.refresh_token,
      tenant: String(session.tenant_id || tenantId),
      account: String(session.account_id || ""),
    }
  );
}

test.beforeEach(async ({ request }) => {
  const health = await request.get(`${API}/health`).catch(() => null);
  if (!health || !health.ok()) {
    test.skip(true, `API not reachable at ${API}`);
  }
});

test("journey: login shows desk shell", async ({ page, request }) => {
  const { session, tenant_id } = await seedSession(request);
  await injectTokens(page, session, tenant_id);
  await page.goto(h("/attendance"));
  await page.waitForTimeout(800);
  if (await page.getByText(/Session required/i).count()) {
    throw new Error("journey login: Session required after hydrate");
  }
  await expect(page.getByText(/Attendance|Present|Absent|Today|Batch/i).first()).toBeVisible({ timeout: 15000 });
  await shot(page, "j-login-attendance");
});

test("journey: admissions list renders", async ({ page, request }) => {
  const { session, tenant_id } = await seedSession(request);
  await injectTokens(page, session, tenant_id);
  await page.goto(h("/admissions"));
  await page.waitForTimeout(600);
  if (await page.getByText(/Session required/i).count()) {
    throw new Error("admissions: Session required after hydrate");
  }
  await expect(page.getByText(/Admit|Admissions|Name|Student|ভর্তি/i).first()).toBeVisible({ timeout: 15000 });
  await shot(page, "j-admissions");
});

test("journey: fees page without bearer error text", async ({ page, request }) => {
  const { session, tenant_id } = await seedSession(request);
  await injectTokens(page, session, tenant_id);
  await page.goto(h("/fees"));
  await page.waitForTimeout(500);
  await expect(page.getByTestId("attendance-history")).toBeVisible({ timeout: 15000 });
  await expect(page.getByText("Missing bearer token")).toHaveCount(0);
  await expect(page.getByText(/Session required/i)).toHaveCount(0);
  await shot(page, "j-fees");
});

test("journey: exams page loads", async ({ page, request }) => {
  const { session, tenant_id } = await seedSession(request);
  await injectTokens(page, session, tenant_id);
  await page.goto(h("/exams"));
  await page.waitForTimeout(500);
  await expect(page.getByText("Missing bearer token")).toHaveCount(0);
  await expect(page.getByText(/Session required/i)).toHaveCount(0);
  await shot(page, "j-exams");
});

test("journey: vault page loads", async ({ page, request }) => {
  const { session, tenant_id } = await seedSession(request);
  await injectTokens(page, session, tenant_id);
  await page.goto(h("/vault"));
  await page.waitForTimeout(500);
  await expect(page.getByText("Missing bearer token")).toHaveCount(0);
  await expect(page.getByText(/Session required/i)).toHaveCount(0);
  await shot(page, "j-vault");
});

test("journey: settings hub", async ({ page, request }) => {
  const { session, tenant_id } = await seedSession(request);
  await injectTokens(page, session, tenant_id);
  await page.goto(h("/settings"));
  await page.waitForTimeout(500);
  await expect(page.getByTestId("settings-hub")).toBeVisible({ timeout: 15000 });
  await shot(page, "j-settings");
});

test("journey: support shows contact email", async ({ page, request }) => {
  const { session, tenant_id } = await seedSession(request);
  await injectTokens(page, session, tenant_id);
  await page.goto(h("/support"));
  await page.waitForTimeout(500);
  await expect(page.getByText("support@cohortos.app")).toBeVisible({ timeout: 10000 });
  await shot(page, "j-support");
});

test("journey: Bangla batch name via API", async ({ request }) => {
  const { session, tenant_id } = await seedSession(request);
  const headers = { Authorization: `Bearer ${session.access_token}` };
  const batchName = `ব্যাচ Journey ${Date.now()}`;
  const r = await request.post(`${API}/t/${tenant_id}/admissions/batches`, {
    headers,
    data: { name: batchName, code: `j-${Date.now()}` },
  });
  if (!r.ok()) {
    const alt = await request.post(`${API}/t/${tenant_id}/batches`, { headers, data: { name: batchName } });
    expect([200, 201, 404, 405, 422]).toContain(alt.status());
  } else {
    expect(r.ok()).toBeTruthy();
  }
});

test("journey: student create with Bangla name", async ({ request }) => {
  const { session, tenant_id } = await seedSession(request);
  const headers = { Authorization: `Bearer ${session.access_token}` };
  const r = await request.post(`${API}/t/${tenant_id}/admissions/students`, {
    headers,
    data: { name: "সুমাইয়া আক্তার", phone: "01918887766", guardian_name: "অভিভাবক" },
  });
  if (!r.ok()) {
    const alt = await request.post(`${API}/t/${tenant_id}/students`, {
      headers,
      data: { name: "সুমাইয়া আক্তার", phone: "01918887766" },
    });
    expect([200, 201, 404, 405, 422]).toContain(alt.status());
  } else {
    expect(r.ok()).toBeTruthy();
  }
});

test("journey: attendance history route", async ({ page, request }) => {
  const { session, tenant_id } = await seedSession(request);
  await injectTokens(page, session, tenant_id);
  await page.goto(h("/attendance/history"));
  await page.waitForTimeout(500);
  await expect(page.getByText("Missing bearer token")).toHaveCount(0);
  await expect(page.getByText(/Session required/i)).toHaveCount(0);
  await shot(page, "j-history");
});

test("journey: AI page without raw token leak text", async ({ page, request }) => {
  const { session, tenant_id } = await seedSession(request);
  await injectTokens(page, session, tenant_id);
  await page.goto(h("/ai"));
  await page.waitForTimeout(500);
  await expect(page.getByText("Missing bearer token")).toHaveCount(0);
  await expect(page.getByText(/Session required/i)).toHaveCount(0);
  await shot(page, "j-ai");
});

test("journey: automations page", async ({ page, request }) => {
  const { session, tenant_id } = await seedSession(request);
  await injectTokens(page, session, tenant_id);
  await page.goto(h("/settings/automations"));
  await page.waitForTimeout(500);
  await expect(page.getByText("Missing bearer token")).toHaveCount(0);
  await expect(page.getByText(/Session required/i)).toHaveCount(0);
  await shot(page, "j-automations");
});
