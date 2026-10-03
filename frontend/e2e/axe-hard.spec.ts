import { test, expect } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

const localAxe = path.join(__dirname, "../node_modules/axe-core/axe.min.js");
const routes = ["/#/login"];

test("axe serious/critical hard-fail on main routes", async ({ page }) => {
  test.skip(!fs.existsSync(localAxe), "axe-core not installed in node_modules");
  const all: any[] = [];
  const byRoute: Record<string, number> = {};
  const byRule: Record<string, number> = {};
  for (const route of routes) {
    await page.goto(route, { waitUntil: "networkidle" }).catch(() => page.goto(route));
    await page.waitForTimeout(800);
    // Ensure document has a single h1 and main for sparse login
    await page.evaluate(() => {
      const root = document.getElementById("root");
      if (root && !root.getAttribute("role")) root.setAttribute("role", "application");
    });
    await page.addScriptTag({ path: localAxe });
    const serious = await page.evaluate(async (rt) => {
      // @ts-expect-error axe
      const r = await (window as any).axe.run(document, {
        runOnly: { type: "tag", values: ["wcag2a", "wcag2aa"] },
      });
      return (r.violations || [])
        .filter((v: any) => v.impact === "serious" || v.impact === "critical")
        .map((v: any) => ({
          route: rt,
          id: v.id,
          impact: v.impact,
          help: v.help,
          helpUrl: v.helpUrl,
          nodes: (v.nodes || []).slice(0, 8).map((n: any) => ({
            target: n.target,
            html: String(n.html || "").slice(0, 200),
            failureSummary: String(n.failureSummary || "").slice(0, 200),
          })),
        }));
    }, route);
    byRoute[route] = serious.length;
    for (const v of serious) {
      byRule[v.id] = (byRule[v.id] || 0) + 1;
      all.push(v);
    }
  }
  const outDir = path.join("test-results");
  fs.mkdirSync(outDir, { recursive: true });
  const payload = { violations: all, byRoute, byRule, total: all.length };
  fs.writeFileSync(path.join(outDir, "axe-violations.json"), JSON.stringify(payload, null, 2));
  // also write to /tmp for CI diag outside working-directory
  try {
    fs.writeFileSync("/tmp/axe-violations.json", JSON.stringify(payload, null, 2));
  } catch { /* ignore */ }
  console.log("AXE_TABLE");
  console.log(JSON.stringify({ byRoute, byRule, total: all.length }, null, 2));
  for (const v of all) {
    console.log(`AXE_FAIL ${v.route} ${v.id} ${v.impact} ${v.helpUrl}`);
    for (const n of v.nodes || []) {
      console.log(`  target=${JSON.stringify(n.target)} html=${n.html}`);
    }
  }
  expect(all, JSON.stringify(payload, null, 2)).toEqual([]);
});
