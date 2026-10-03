import { test, expect } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

const localAxe = path.join(__dirname, "../node_modules/axe-core/axe.min.js");
const routes = ["/#/login", "/#/"];

test("axe serious/critical hard-fail on main routes", async ({ page }) => {
  test.skip(!fs.existsSync(localAxe), "axe-core not installed in node_modules");
  const all: any[] = [];
  for (const route of routes) {
    await page.goto(route);
    await page.waitForTimeout(500);
    await page.addScriptTag({ path: localAxe });
    const serious = await page.evaluate(async () => {
      // @ts-expect-error axe
      const r = await (window as any).axe.run(document, {
        runOnly: { type: "tag", values: ["wcag2a", "wcag2aa"] },
      });
      return (r.violations || [])
        .filter((v: any) => v.impact === "serious" || v.impact === "critical")
        .map((v: any) => ({
          route: location.hash,
          id: v.id,
          impact: v.impact,
          help: v.help,
          helpUrl: v.helpUrl,
          nodes: (v.nodes || []).slice(0, 5).map((n: any) => ({
            target: n.target,
            html: (n.html || "").slice(0, 120),
          })),
        }));
    });
    all.push(...serious);
  }
  const outDir = path.join("test-results");
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(path.join(outDir, "axe-violations.json"), JSON.stringify(all, null, 2));
  expect(all, JSON.stringify(all, null, 2)).toEqual([]);
});
