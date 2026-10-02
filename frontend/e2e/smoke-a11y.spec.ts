import { test, expect } from "@playwright/test";

test.describe("a11y + phone viewport", () => {
  test("student join at 360x640 no horizontal overflow", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 640 });
    await page.goto("/#/login");
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 8);
  });

  test("support page body renders on phone", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 640 });
    await page.goto("/#/support");
    await page.waitForTimeout(300);
    const body = await page.locator("body").innerText();
    expect(body.length).toBeGreaterThan(10);
  });
});
