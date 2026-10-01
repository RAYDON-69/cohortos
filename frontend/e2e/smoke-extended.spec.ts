/**
 * Extended desk smoke (P24–P26b): voice, class workspace, broadcast, call desk.
 * Runs separately so failures cannot mask the core gate in smoke.spec.ts.
 */
import { test, expect } from "@playwright/test";
import path from "path";
import fs from "fs";

const API = process.env.COHORTOS_API_BASE || "http://127.0.0.1:8741";
const PHONE =
  process.env.COHORTOS_E2E_PHONE ||
  `0178${String(Date.now()).slice(-8)}`;

const shotDir = path.join("test-results", "smoke-shots");
fs.mkdirSync(shotDir, { recursive: true });

function h(route: string): string {
  const p = route.startsWith("/") ? route : `/${route}`;
  return `/#${p}`;
}

async function shot(page: import("@playwright/test").Page, name: string) {
  try {
    await page.screenshot({ path: path.join(shotDir, `${name}.png`), fullPage: true });
  } catch {
    /* ignore */
  }
}

async function seedSession(request: import("@playwright/test").APIRequestContext) {
  const trialRes = await request.post(`${API}/auth/centre-trial`, {
    data: {
      centre_name: `E2E Ext ${Date.now()}`,
      owner_phone: PHONE,
      owner_name: "E2E Owner",
      student_count: 1,
    },
  });
  const trialText = await trialRes.text();
  if (!trialRes.ok()) throw new Error(`centre-trial ${trialRes.status()}: ${trialText}`);
  const trial = JSON.parse(trialText);
  const otpRes = await request.post(`${API}/auth/request-otp`, {
    data: { phone: PHONE, tenant_id: trial.tenant_id },
  });
  const otpBody = await otpRes.json();
  const code = String(otpBody._test_code || "");
  if (!code) throw new Error("missing _test_code");
  const verifyRes = await request.post(`${API}/auth/verify-otp`, {
    data: {
      phone: PHONE,
      code,
      otp_id: otpBody.otp_id,
      tenant_id: trial.tenant_id,
    },
  });
  const session = await verifyRes.json();
  if (!session.access_token) throw new Error("no access_token");
  return { trial, session, tenantId: String(session.tenant_id || trial.tenant_id) };
}

test.describe.configure({ mode: "serial" });

test("extended — voice, class, broadcast, call desk", async ({ page, request }) => {
  // When explicitly disabled, skip cleanly (does not fail the job)
  if (process.env.COHORTOS_E2E_EXTENDED === "0") {
    test.skip(true, "COHORTOS_E2E_EXTENDED=0");
  }
  const health = await request.get(`${API}/health`).catch(() => null);
  if (!health || !health.ok()) {
    test.skip(true, `API not reachable at ${API}/health`);
  }

  const { session, tenantId } = await seedSession(request);
  const headers = { Authorization: `Bearer ${session.access_token}` };

  await page.goto(h("/login"));
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
      tenant: tenantId,
      account: String(session.account_id || ""),
    }
  );

  // P24 voice
  const vScript = await request.post(`${API}/t/${tenantId}/voice/script`, {
    headers,
    data: {
      student_name: "রহিম E2E",
      phone: "01711112222",
      purpose: "fee_reminder",
      amount_bdt: 500,
      language: "bn",
    },
  });
  if (!vScript.ok()) throw new Error(`voice/script ${vScript.status()} ${await vScript.text()}`);
  const vs = await vScript.json();
  if (!vs.script || !vs.script_id) throw new Error(`voice script missing: ${JSON.stringify(vs)}`);

  const vSum = await request.post(`${API}/t/${tenantId}/voice/summarize`, {
    headers,
    data: {
      call_notes: "Parent will pay tomorrow",
      student_name: "রহিম E2E",
      purpose: "fee_reminder",
    },
  });
  if (!vSum.ok()) throw new Error(`voice/summarize ${vSum.status()}`);
  const vsum = await vSum.json();
  if (!vsum.summary) throw new Error(`voice summary missing`);

  const badCall = await request.post(`${API}/t/${tenantId}/voice/request-call`, {
    headers,
    data: { phone: "01711112222", script: vs.script },
  });
  if (badCall.ok()) throw new Error("request-call without human_action_id must fail");

  // P25 interactive class session
  const cls = await request.post(`${API}/t/${tenantId}/classes/sessions`, {
    headers,
    data: { batch_id: "e2e-batch-1", title: "E2E Physics", mode: "interactive" },
  });
  if (!cls.ok()) throw new Error(`classes/sessions create ${cls.status()} ${await cls.text()}`);
  const classCreated = await cls.json();
  if (!classCreated.id || !classCreated.room) {
    throw new Error(`session shape: ${JSON.stringify(classCreated)}`);
  }

  const join = await request.post(`${API}/t/${tenantId}/classes/sessions/${classCreated.id}/join`, {
    headers,
    data: { role: "participant", display_name: "E2E Student" },
  });
  if (!join.ok()) throw new Error(`join ${join.status()} body=${await join.text()}`);
  const j = await join.json();
  if (!j.join_url || !j.token || !String(j.join_url).includes(classCreated.room)) {
    throw new Error(`join_url invalid: ${JSON.stringify(j)}`);
  }

  // P26b BROADCAST mode — external stream URL, no Jitsi room required for students
  const bcast = await request.post(`${API}/t/${tenantId}/classes/sessions`, {
    headers,
    data: {
      batch_id: "e2e-batch-1",
      title: "E2E Broadcast বাংলা",
      mode: "broadcast",
      broadcast_url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    },
  });
  if (!bcast.ok()) throw new Error(`broadcast create ${bcast.status()} ${await bcast.text()}`);
  const bcastSession = await bcast.json();
  if (bcastSession.mode !== "broadcast") {
    throw new Error(`expected mode=broadcast got ${JSON.stringify(bcastSession)}`);
  }
  if (!bcastSession.broadcast_url) throw new Error("broadcast_url missing");

  const bJoin = await request.post(`${API}/t/${tenantId}/classes/sessions/${bcastSession.id}/join`, {
    headers,
    data: { role: "participant", display_name: "Viewer", student_id: "stu-b1" },
  });
  if (!bJoin.ok()) throw new Error(`broadcast join ${bJoin.status()}`);
  const bj = await bJoin.json();
  if (bj.mode !== "broadcast" || !String(bj.join_url || "").includes("youtube")) {
    throw new Error(`broadcast join should return stream URL: ${JSON.stringify(bj)}`);
  }

  // Poll + raise-hand
  const rh = await request.post(`${API}/t/${tenantId}/classes/sessions/${classCreated.id}/raise-hand`, {
    headers,
    data: { student_id: "stu1", name: "রহিম" },
  });
  if (!rh.ok()) throw new Error(`raise-hand ${rh.status()} ${await rh.text()}`);
  const poll = await request.post(`${API}/t/${tenantId}/classes/sessions/${classCreated.id}/polls`, {
    headers,
    data: { question: "আজকের টপিক বুঝেছেন?", options: ["হ্যাঁ", "না"] },
  });
  if (!poll.ok()) throw new Error(`poll ${poll.status()} ${await poll.text()}`);

  // Device tier LITE vs FULL
  const lite = await request.post(`${API}/t/${tenantId}/classes/device-tier`, {
    headers,
    data: { deviceMemory: 4, hardwareConcurrency: 2, downlink: 1, effectiveType: "2g" },
  });
  if (!lite.ok()) throw new Error(`device-tier ${lite.status()}`);
  const liteJ = await lite.json();
  if (liteJ.tier !== "lite" || liteJ.whiteboard !== false) {
    throw new Error(`expected LITE without whiteboard: ${JSON.stringify(liteJ)}`);
  }
  const full = await request.post(`${API}/t/${tenantId}/classes/device-tier`, {
    headers,
    data: { deviceMemory: 16, hardwareConcurrency: 8, downlink: 50 },
  });
  const fullJ = await full.json();
  if (fullJ.tier !== "full" || fullJ.whiteboard !== true) {
    throw new Error(`expected FULL with whiteboard: ${JSON.stringify(fullJ)}`);
  }

  // Timetable + absentees + call desk
  const tt = await request.post(`${API}/t/${tenantId}/classes/timetable/generate`, {
    headers,
    data: { batch_id: "e2e-batch-1", weekday: 1, time: "16:00", weeks: 1, title: "E2E Timetable" },
  });
  if (!tt.ok()) throw new Error(`timetable ${tt.status()} ${await tt.text()}`);

  const abs = await request.post(
    `${API}/t/${tenantId}/classes/sessions/${classCreated.id}/notify-absentees`,
    {
      headers,
      data: { present_ids: ["stu1"], roster_ids: ["stu1", "stu2"] },
    }
  );
  if (!abs.ok()) throw new Error(`absentees ${abs.status()}`);
  const absJ = await abs.json();
  if ((absJ.absent_count || 0) < 1) throw new Error("expected absentee notice");

  const q = await request.post(`${API}/t/${tenantId}/call-desk/queue`, {
    headers,
    data: { fee_dues: [{ name: "E2E করিম", phone: "01711112222", detail: "due" }] },
  });
  if (!q.ok()) throw new Error(`call-desk queue ${q.status()}`);
  const card = ((await q.json()).cards || [])[0];
  if (!card) throw new Error("no call desk card");
  const out = await request.post(`${API}/t/${tenantId}/call-desk/outcome`, {
    headers,
    data: {
      card_id: card.id,
      outcome: "no_answer",
      human_action_id: "e2e-human-1",
      notes: "busy",
    },
  });
  if (!out.ok()) throw new Error(`outcome ${out.status()} ${await out.text()}`);

  // Demo seed + remove
  const demo = await request.post(`${API}/t/${tenantId}/demo/load`, { headers });
  if (!demo.ok()) throw new Error(`demo/load ${demo.status()} ${await demo.text()}`);
  const demoJ = await demo.json();
  if (demoJ.marker !== "DEMO_COHORTOS") throw new Error("demo marker missing");

  const wb = await request.put(`${API}/t/${tenantId}/classes/sessions/${classCreated.id}/whiteboard`, {
    headers,
    data: { scene: JSON.stringify({ elements: [{ id: "e1" }] }) },
  });
  if (!wb.ok()) throw new Error(`whiteboard save ${wb.status()} ${await wb.text()}`);
  const wbg = await request.get(`${API}/t/${tenantId}/classes/sessions/${classCreated.id}/whiteboard`, { headers });
  if (!wbg.ok()) throw new Error(`whiteboard load ${wbg.status()}`);

  const bak = await request.post(`${API}/t/${tenantId}/backup`, { headers });
  if (!bak.ok()) throw new Error(`backup ${bak.status()}`);
  const bakJ = await bak.json();
  if (!bakJ.checksum_sha256) throw new Error("backup checksum missing");

  const rm = await request.post(`${API}/t/${tenantId}/demo/remove`, { headers });
  if (!rm.ok()) throw new Error(`demo/remove ${rm.status()}`);

  // 4GB LITE heap metric (best-effort in Chromium)
  const client = await page.context().newCDPSession(page);
  try {
    await client.send("Emulation.setCPUThrottlingRate", { rate: 4 });
  } catch { /* ignore */ }
  const t0 = Date.now();
  await page.goto(h("/classes"));
  await page.waitForTimeout(1000);
  await page.goto(h("/call-desk"));
  await page.waitForTimeout(1000);
  const loadMs = Date.now() - t0;
  const heap = await page.evaluate(() => {
    const m = (performance as any).memory;
    return m ? m.usedJSHeapSize : 0;
  });
  const fs = await import("fs");
  fs.writeFileSync(
    "test-results/lite-heap.json",
    JSON.stringify({ usedJSHeapSize: heap, loadMs, tier: "lite-throttle-4x" }, null, 2)
  );
  // Budget from measured + 50% headroom once known; soft assert < 120MB
  if (heap > 0 && heap > 120 * 1024 * 1024) {
    throw new Error(`LITE heap too high: ${heap}`);
  }

  // Empty-DB-safe page mounts
  for (const route of ["/classes", "/call-desk", "/voice"]) {
    await page.goto(h(route));
    await page.waitForTimeout(500);
    await expect(page.getByText(/Missing bearer token/i)).toHaveCount(0);
    await shot(page, `ext-${route.replace(/\//g, "")}`);
  }
});
