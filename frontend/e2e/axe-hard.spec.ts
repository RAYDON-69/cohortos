import { test, expect } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

const localAxe = path.join(__dirname, "../node_modules/axe-core/axe.min.js");

test("axe serious/critical hard-fail on login (vendored)", async ({ page }) => {
  test.skip(!fs.existsSync(localAxe), "axe-core not installed in node_modules");
  await page.goto("/#/login");
  await page.addScriptTag({ path: localAxe });
  const serious = await page.evaluate(async () => {
    // @ts-expect-error axe
    const r = await (window as any).axe.run(document, {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa"] },
    });
    return (r.violations || []).filter((v: any) => v.impact === "serious" || v.impact === "critical");
  });
  expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
});
