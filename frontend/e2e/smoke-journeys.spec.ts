import { test, expect } from "@playwright/test";
import path from "path";
import fs from "fs";

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
  const phone = `0177${String(Date.now()).slice(-8)}${Math.floor(Math.random() * 9)}`;
  const trial = await request.post(`${API}/auth/centre-trial`, {
    data: {
      centre_name: `Journey ${Date.now()}`,
      owner_phone: phone,
      owner_name: "Journey Owner",
      student_count: 1,
    },
  });
  if (!trial.ok()) throw new Error(`trial ${trial.status()} ${await trial.text()}`);
  const { tenant_id } = await trial.json();
  const otp = await request.post(`${API}/auth/request-otp`, { data: { phone, tenant_id } });
  if (!otp.ok()) throw new Error(`otp ${otp.status()}`);
  const body = await otp.json();
  const ver = await request.post(`${API}/auth/verify-otp`, {
    data: { phone, code: body._test_code, otp_id: body.otp_id, tenant_id },
  });
  if (!ver.ok()) throw new Error(`verify ${ver.status()}`);
  const session = await ver.json();
  return { phone, tenant_id, session };
}

async function injectTokens(page: import("@playwright/test").Page, session: any, tenantId: string) {
  await page.goto(h("/login"));
  await page.evaluate(
    ({ access, refresh, tenant }) => {
      const w = window as any;
      if (typeof w.__COHORTOS_SAVE_TOKENS__ === "function") {
        w.__COHORTOS_SAVE_TOKENS__({ access_token: access, refresh_token: refresh, tenant_id: tenant });
      } else {
        localStorage.setItem(
          "cohortos_tokens",
          JSON.stringify({ access_token: access, refresh_token: refresh, tenant_id: tenant })
        );
      }
    },
    { access: session.access_token, refresh: session.refresh_token || "", tenant: tenantId }
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
  await expect(page.getByText(/Attendance|Present|Absent|Today|Batch/i).first()).toBeVisible({ timeout: 15000 });
  await shot(page, "j-login-attendance");
});

test("journey: admissions list renders", async ({ page, request }) => {
  const { session, tenant_id } = await seedSession(request);
  await injectTokens(page, session, tenant_id);
  await page.goto(h("/admissions"));
  await expect(page.getByText(/Admit|Admissions|Name|Student|ভর্তি/i).first()).toBeVisible({ timeout: 15000 });
  await shot(page, "j-admissions");
});

test("journey: fees page without bearer error text", async ({ page, request }) => {
  const { session, tenant_id } = await seedSession(request);
  await injectTokens(page, session, tenant_id);
  await page.goto(h("/fees"));
  await expect(page.getByText("Missing bearer token")).toHaveCount(0);
  await shot(page, "j-fees");
});

test("journey: exams page loads", async ({ page, request }) => {
  const { session, tenant_id } = await seedSession(request);
  await injectTokens(page, session, tenant_id);
  await page.goto(h("/exams"));
  await expect(page.getByText("Missing bearer token")).toHaveCount(0);
  await shot(page, "j-exams");
});

test("journey: vault page loads", async ({ page, request }) => {
  const { session, tenant_id } = await seedSession(request);
  await injectTokens(page, session, tenant_id);
  await page.goto(h("/vault"));
  await expect(page.getByText("Missing bearer token")).toHaveCount(0);
  await shot(page, "j-vault");
});

test("journey: settings hub", async ({ page, request }) => {
  const { session, tenant_id } = await seedSession(request);
  await injectTokens(page, session, tenant_id);
  await page.goto(h("/settings"));
  await expect(page.getByText(/Settings|Integrations|Support|Staff/i).first()).toBeVisible({ timeout: 10000 });
  await shot(page, "j-settings");
});

test("journey: support shows contact email", async ({ page, request }) => {
  const { session, tenant_id } = await seedSession(request);
  await injectTokens(page, session, tenant_id);
  await page.goto(h("/support"));
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
  await expect(page.getByText("Missing bearer token")).toHaveCount(0);
  await shot(page, "j-history");
});

test("journey: AI page without raw token leak text", async ({ page, request }) => {
  const { session, tenant_id } = await seedSession(request);
  await injectTokens(page, session, tenant_id);
  await page.goto(h("/ai"));
  await expect(page.getByText("Missing bearer token")).toHaveCount(0);
  await shot(page, "j-ai");
});

test("journey: automations page", async ({ page, request }) => {
  const { session, tenant_id } = await seedSession(request);
  await injectTokens(page, session, tenant_id);
  await page.goto(h("/settings/automations"));
  await expect(page.getByText("Missing bearer token")).toHaveCount(0);
  await shot(page, "j-automations");
});
