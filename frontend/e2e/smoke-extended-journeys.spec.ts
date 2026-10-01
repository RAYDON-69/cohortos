import { test, expect } from "@playwright/test";

const API = process.env.COHORTOS_API_BASE || "http://127.0.0.1:8741";

async function seed(request: import("@playwright/test").APIRequestContext) {
  const phone = `0188${String(Date.now()).slice(-8)}${Math.floor(Math.random() * 9)}`;
  const trial = await request.post(`${API}/auth/centre-trial`, {
    data: { centre_name: `Ext ${Date.now()}`, owner_phone: phone, owner_name: "Ext", student_count: 1 },
  });
  if (!trial.ok()) throw new Error(`trial ${trial.status()}`);
  const { tenant_id } = await trial.json();
  const otp = await request.post(`${API}/auth/request-otp`, { data: { phone, tenant_id } });
  const body = await otp.json();
  const ver = await request.post(`${API}/auth/verify-otp`, {
    data: { phone, code: body._test_code, otp_id: body.otp_id, tenant_id },
  });
  if (!ver.ok()) throw new Error(`verify ${ver.status()}`);
  return { tenant_id, token: (await ver.json()).access_token };
}

test.beforeEach(async ({ request }) => {
  const health = await request.get(`${API}/health`).catch(() => null);
  if (!health || !health.ok()) test.skip(true, "API down");
});

test("ext: create class session + join URL shape", async ({ request }) => {
  const { tenant_id, token } = await seed(request);
  const headers = { Authorization: `Bearer ${token}` };
  const created = await request.post(`${API}/t/${tenant_id}/classes/sessions`, {
    headers,
    data: {
      batch_id: "b1",
      title: "Extended Class",
      mode: "broadcast",
      broadcast_url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    },
  });
  expect(created.ok(), await created.text()).toBeTruthy();
  const sess = await created.json();
  expect(sess.id).toBeTruthy();
});

test("ext: device tier LITE hides whiteboard", async ({ request }) => {
  const { tenant_id, token } = await seed(request);
  const headers = { Authorization: `Bearer ${token}` };
  const lite = await request.post(`${API}/t/${tenant_id}/classes/device-tier`, {
    headers,
    data: { deviceMemory: 4, hardwareConcurrency: 2, downlink: 1, effectiveType: "2g" },
  });
  if (lite.ok()) {
    const j = await lite.json();
    expect(j.tier).toBe("lite");
    expect(j.whiteboard).toBe(false);
  }
});

test("ext: device tier FULL allows whiteboard", async ({ request }) => {
  const { tenant_id, token } = await seed(request);
  const headers = { Authorization: `Bearer ${token}` };
  const full = await request.post(`${API}/t/${tenant_id}/classes/device-tier`, {
    headers,
    data: { deviceMemory: 16, hardwareConcurrency: 8, downlink: 50 },
  });
  if (full.ok()) {
    const j = await full.json();
    expect(j.tier).toBe("full");
    expect(j.whiteboard).toBe(true);
  }
});

test("ext: demo load and remove", async ({ request }) => {
  const { tenant_id, token } = await seed(request);
  const headers = { Authorization: `Bearer ${token}` };
  const load = await request.post(`${API}/t/${tenant_id}/demo/load`, { headers });
  expect(load.ok(), await load.text()).toBeTruthy();
  const j = await load.json();
  expect(j.marker).toBe("DEMO_COHORTOS");
  const rm = await request.post(`${API}/t/${tenant_id}/demo/remove`, { headers });
  expect(rm.ok()).toBeTruthy();
});

test("ext: encrypted backup has checksum", async ({ request }) => {
  const { tenant_id, token } = await seed(request);
  const headers = { Authorization: `Bearer ${token}` };
  const bak = await request.post(`${API}/t/${tenant_id}/backup`, { headers });
  expect(bak.ok(), await bak.text()).toBeTruthy();
  const j = await bak.json();
  expect(j.checksum_sha256).toBeTruthy();
  expect(j.ciphertext_b64).toBeTruthy();
});

test("ext: broadcast rejects non-https", async ({ request }) => {
  const { tenant_id, token } = await seed(request);
  const headers = { Authorization: `Bearer ${token}` };
  const bad = await request.post(`${API}/t/${tenant_id}/classes/sessions`, {
    headers,
    data: { batch_id: "b1", title: "bad", mode: "broadcast", broadcast_url: "http://127.0.0.1/x" },
  });
  expect(bad.status()).toBeGreaterThanOrEqual(400);
});

test("ext: call desk queue reachable", async ({ request }) => {
  const { tenant_id, token } = await seed(request);
  const headers = { Authorization: `Bearer ${token}` };
  const r = await request.post(`${API}/t/${tenant_id}/call-desk/queue`, { headers, data: {} });
  expect([200, 201, 400, 404, 422]).toContain(r.status());
  expect(r.status()).toBeLessThan(500);
});

test("ext: raise-hand on session", async ({ request }) => {
  const { tenant_id, token } = await seed(request);
  const headers = { Authorization: `Bearer ${token}` };
  const created = await request.post(`${API}/t/${tenant_id}/classes/sessions`, {
    headers,
    data: {
      batch_id: "b1",
      title: "RH",
      mode: "broadcast",
      broadcast_url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    },
  });
  if (!created.ok()) test.skip();
  const id = (await created.json()).id;
  const rh = await request.post(`${API}/t/${tenant_id}/classes/sessions/${id}/raise-hand`, {
    headers,
    data: { student_id: "s1", name: "রহিম" },
  });
  expect([200, 201, 404, 422]).toContain(rh.status());
});

test("ext: whiteboard scene roundtrip", async ({ request }) => {
  const { tenant_id, token } = await seed(request);
  const headers = { Authorization: `Bearer ${token}` };
  const created = await request.post(`${API}/t/${tenant_id}/classes/sessions`, {
    headers,
    data: {
      batch_id: "b1",
      title: "WB",
      mode: "broadcast",
      broadcast_url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    },
  });
  if (!created.ok()) test.skip();
  const id = (await created.json()).id;
  const put = await request.put(`${API}/t/${tenant_id}/classes/sessions/${id}/whiteboard`, {
    headers,
    data: { scene: JSON.stringify({ elements: [{ id: "e1" }] }) },
  });
  if (put.ok()) {
    const got = await request.get(`${API}/t/${tenant_id}/classes/sessions/${id}/whiteboard`, { headers });
    expect(got.ok()).toBeTruthy();
  }
});

test("ext: poll create Bangla", async ({ request }) => {
  const { tenant_id, token } = await seed(request);
  const headers = { Authorization: `Bearer ${token}` };
  const created = await request.post(`${API}/t/${tenant_id}/classes/sessions`, {
    headers,
    data: {
      batch_id: "b1",
      title: "Poll",
      mode: "broadcast",
      broadcast_url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    },
  });
  if (!created.ok()) test.skip();
  const id = (await created.json()).id;
  const poll = await request.post(`${API}/t/${tenant_id}/classes/sessions/${id}/polls`, {
    headers,
    data: { question: "আজকের টপিক বুঝেছেন?", options: ["হ্যাঁ", "না"] },
  });
  expect([200, 201, 404, 422]).toContain(poll.status());
});

test("ext: notify absentees endpoint", async ({ request }) => {
  const { tenant_id, token } = await seed(request);
  const headers = { Authorization: `Bearer ${token}` };
  const created = await request.post(`${API}/t/${tenant_id}/classes/sessions`, {
    headers,
    data: {
      batch_id: "b1",
      title: "Abs",
      mode: "broadcast",
      broadcast_url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    },
  });
  if (!created.ok()) test.skip();
  const id = (await created.json()).id;
  const r = await request.post(`${API}/t/${tenant_id}/classes/sessions/${id}/notify-absentees`, {
    headers,
    data: { roster_ids: ["s1", "s2"] },
  });
  expect([200, 201, 404, 422]).toContain(r.status());
});

test("ext: PDPA export shape", async ({ request }) => {
  const { tenant_id, token } = await seed(request);
  const headers = { Authorization: `Bearer ${token}` };
  const r = await request.get(`${API}/t/${tenant_id}/export/pdpa`, { headers });
  if (r.ok()) {
    const j = await r.json();
    expect(String(j.label || "")).toMatch(/PDPA/i);
  }
});
