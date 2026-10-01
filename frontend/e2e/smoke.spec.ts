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

  // --- RAG proof: seed vault text, query AI, answer must cite unique token ---
  const RAG_TOKEN = `E2E_RAG_TOKEN_${Date.now()}`;
  const tenantForApi = String(session.tenant_id || trial.tenant_id);
  const vaultCreate = await request.post(`${API}/t/${tenantForApi}/vault`, {
    headers: { Authorization: `Bearer ${session.access_token}` },
    data: {
      title: `E2E Vault Note ${RAG_TOKEN}`,
      resource_type: "pdf",
      topic: "e2e",
      description: `This confidential centre note contains the marker ${RAG_TOKEN} for retrieval tests.`,
    },
  });
  if (!vaultCreate.ok()) {
    const body = await vaultCreate.text();
    throw new Error(`vault create failed ${vaultCreate.status()}: ${body}`);
  }
  const aiRes = await request.post(`${API}/t/${tenantForApi}/ai/query`, {
    headers: { Authorization: `Bearer ${session.access_token}` },
    data: { question: `What is the marker token in the E2E vault note? Look for E2E_RAG_TOKEN`, session_id: "e2e-smoke" },
  });
  const aiText = await aiRes.text();
  if (!aiRes.ok()) {
    throw new Error(`ai/query failed ${aiRes.status()}: ${aiText}`);
  }
  const aiJson = JSON.parse(aiText);
  const answer = String(aiJson.answer || "");
  if (!answer.includes(RAG_TOKEN) && !(JSON.stringify(aiJson.grounded || {}).includes(RAG_TOKEN))) {
    throw new Error(
      `RAG did not ground on seeded vault content. answer=${answer.slice(0, 300)} grounded=${JSON.stringify(aiJson.grounded).slice(0, 400)}`
    );
  }

  // --- Automation fire proof: create rule, run, log must contain rule_run ---
  const ruleRes = await request.post(`${API}/t/${tenantForApi}/automations/rules`, {
    headers: { Authorization: `Bearer ${session.access_token}` },
    data: {
      name: `E2E Fire ${Date.now()}`,
      enabled: true,
      trigger: { type: "manual" },
      conditions: [],
      actions: [{ type: "log_only", params: { note: "e2e" } }],
    },
  });
  const ruleText = await ruleRes.text();
  if (!ruleRes.ok()) {
    throw new Error(`create rule failed ${ruleRes.status()}: ${ruleText}`);
  }
  const ruleJson = JSON.parse(ruleText);
  const ruleId = ruleJson.rule?.id || ruleJson.id;
  if (!ruleId) {
    throw new Error(`create rule missing id: ${ruleText}`);
  }
  const runRes = await request.post(`${API}/t/${tenantForApi}/automations/rules/${ruleId}/run`, {
    headers: { Authorization: `Bearer ${session.access_token}` },
    data: {},
  });
  const runText = await runRes.text();
  if (!runRes.ok()) {
    throw new Error(`run rule failed ${runRes.status()}: ${runText}`);
  }
  const logRes = await request.get(`${API}/t/${tenantForApi}/automations/log`, {
    headers: { Authorization: `Bearer ${session.access_token}` },
  });
  const logJson = await logRes.json();
  const log = logJson.log || [];
  const fired = log.some(
    (e: { type?: string; rule_id?: string }) =>
      e.type === "rule_run" && String(e.rule_id) === String(ruleId)
  );
  if (!fired) {
    throw new Error(`automation did not fire; log=${JSON.stringify(log).slice(0, 500)}`);
  }

  // --- Function-calling proof: Copilot creates a rule via structured tool_calls ---
  const toolQ = `Please create an automation rule named "E2E Copilot Rule ${Date.now()}" for fee reminders`;
  const toolAi = await request.post(`${API}/t/${tenantForApi}/ai/query`, {
    headers: { Authorization: `Bearer ${session.access_token}` },
    data: { question: toolQ, session_id: "e2e-tools", confirm_tools: true },
  });
  const toolText = await toolAi.text();
  if (!toolAi.ok()) {
    throw new Error(`tool ai/query failed ${toolAi.status()}: ${toolText}`);
  }
  const toolJson = JSON.parse(toolText);
  const tr = toolJson.grounded?.tool_results || [];
  const created = tr.some((r: { ok?: boolean; name?: string }) => r.ok && r.name === "create_automation_rule");
  if (!created) {
    throw new Error(
      `function-calling did not create rule; tool_results=${JSON.stringify(tr).slice(0, 400)} answer=${String(toolJson.answer || "").slice(0, 200)}`
    );
  }



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

  // CSV import preview API
  const csv = "name,phone\nImportStu,01911112222\n";
  const imp = await request.post(`${API}/t/${tenantForApi}/admissions/import/preview`, {
    headers: { Authorization: `Bearer ${session.access_token}`, "Content-Type": "text/csv" },
    data: csv,
  });
  if (!imp.ok()) throw new Error(`import preview ${imp.status()}`);
  const impJ = await imp.json();
  if ((impJ.valid || 0) < 1) throw new Error(`import preview invalid: ${JSON.stringify(impJ)}`);

  // Scheduled rule dry-run
  const sched = await request.post(`${API}/t/${tenantForApi}/automations/rules`, {
    headers: { Authorization: `Bearer ${session.access_token}` },
    data: {
      name: `E2E Schedule ${Date.now()}`,
      enabled: true,
      trigger: { type: "schedule.daily" },
      conditions: [{ field: "fee.days_overdue", op: ">=", value: 7 }],
      actions: [{ type: "log_only", params: {} }],
    },
  });
  const schedJ = await sched.json();
  const sid = schedJ.rule?.id;
  if (sid) {
    const dry = await request.post(`${API}/t/${tenantForApi}/automations/rules/${sid}/dry-run`, {
      headers: { Authorization: `Bearer ${session.access_token}` },
      data: { "fee.days_overdue": 10 },
    });
    if (!dry.ok()) throw new Error(`dry-run failed ${dry.status()}`);
    const dryJ = await dry.json();
    if (!dryJ.dry_run && dryJ.type !== "rule_run_dry") {
      throw new Error(`expected dry_run log entry: ${JSON.stringify(dryJ)}`);
    }
  }


  // P24 Voice assist — script + summary (no autodial)
  const vScript = await request.post(`${API}/t/${tenantForApi}/voice/script`, {
    headers: { Authorization: `Bearer ${session.access_token}` },
    data: {
      student_name: "E2E Student",
      phone: "01711112222",
      purpose: "fee_reminder",
      amount_bdt: 500,
      language: "bn",
    },
  });
  if (!vScript.ok()) throw new Error(`voice/script ${vScript.status()} ${await vScript.text()}`);
  const vs = await vScript.json();
  if (!vs.script || !vs.script_id) throw new Error(`voice script missing: ${JSON.stringify(vs)}`);

  const vSum = await request.post(`${API}/t/${tenantForApi}/voice/summarize`, {
    headers: { Authorization: `Bearer ${session.access_token}` },
    data: {
      call_notes: "Parent will pay tomorrow morning",
      student_name: "E2E Student",
      purpose: "fee_reminder",
    },
  });
  if (!vSum.ok()) throw new Error(`voice/summarize ${vSum.status()}`);
  const vsum = await vSum.json();
  if (!vsum.summary) throw new Error(`voice summary missing: ${JSON.stringify(vsum)}`);

  // Hard gate: request-call without human_action_id must fail
  const badCall = await request.post(`${API}/t/${tenantForApi}/voice/request-call`, {
    headers: { Authorization: `Bearer ${session.access_token}` },
    data: { phone: "01711112222", script: vs.script },
  });
  if (badCall.ok()) throw new Error("request-call without human_action_id must not succeed");

  await page.goto(h("/voice"));
  await page.waitForTimeout(800);
  await shot(page, "14-voice-assist");
  // P25 Class workspace — create session, join URL, list by batch
  const cls = await request.post(`${API}/t/${tenantForApi}/classes/sessions`, {
    headers: { Authorization: `Bearer ${session.access_token}` },
    data: { batch_id: "e2e-batch-1", title: "E2E Physics" },
  });
  if (!cls.ok()) throw new Error(`classes/sessions create ${cls.status()} ${await cls.text()}`);
  const created = await cls.json();
  if (!created.id || !created.room) throw new Error(`session shape: ${JSON.stringify(created)}`);

  const join = await request.post(`${API}/t/${tenantForApi}/classes/sessions/${created.id}/join`, {
    headers: { Authorization: `Bearer ${session.access_token}` },
    data: { role: "participant", display_name: "E2E Student" },
  });
  if (!join.ok()) throw new Error(`join ${join.status()}`);
  const j = await join.json();
  if (!j.join_url || !j.token || !String(j.join_url).includes(created.room)) {
    throw new Error(`join_url invalid: ${JSON.stringify(j)}`);
  }

  const listed = await request.get(`${API}/t/${tenantForApi}/classes/sessions?batch_id=e2e-batch-1`, {
    headers: { Authorization: `Bearer ${session.access_token}` },
  });
  if (!listed.ok()) throw new Error(`list sessions ${listed.status()}`);
  const lj = await listed.json();
  if (!(lj.sessions || []).some((s: { id: string }) => s.id === created.id)) {
    throw new Error(`session not listed for batch: ${JSON.stringify(lj)}`);
  }

  await page.goto(h("/classes"));
  await page.waitForTimeout(600);
  await shot(page, "15-class-workspace");

  await expect(page.getByText("support@cohortos.app")).toBeVisible();
});
