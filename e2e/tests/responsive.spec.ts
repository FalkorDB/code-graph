import { test, expect } from "@playwright/test";
import BrowserWrapper from "../infra/ui/browserWrapper";
import CodeGraph from "../logic/POM/codeGraph";
import urls from "../config/urls.json";

const baseUrl = process.env.CODE_GRAPH_BASE_URL || urls.baseUrl;

test.describe("Responsive layout tests", () => {
  let browser: BrowserWrapper;

  test.beforeAll(async () => {
    browser = new BrowserWrapper();
  });

  test.afterAll(async () => {
    await browser.closeBrowser();
  });

  test("keeps the mobile selector wide and fills the visible viewport height", async () => {
    await browser.createNewPage(CodeGraph);
    const page = await browser.getPage();

    await page.setViewportSize({ width: 390, height: 844 });
    await browser.navigateTo(baseUrl);

    const selectorMetrics = await page.locator('#mobile [role="combobox"]').evaluate((element) => {
      const rect = element.getBoundingClientRect();

      return {
        width: rect.width,
        left: rect.left,
        right: rect.right,
        viewportWidth: window.innerWidth,
      };
    });

    expect(selectorMetrics.width).toBeGreaterThanOrEqual(selectorMetrics.viewportWidth - 24);
    expect(selectorMetrics.left).toBeLessThanOrEqual(12);
    expect(selectorMetrics.right).toBeGreaterThanOrEqual(selectorMetrics.viewportWidth - 12);

    const heightMetrics = await page.evaluate(() => {
      const root = document.getElementById("root");
      const main = document.querySelector("main");

      return {
        viewportHeight: window.innerHeight,
        rootHeight: root?.getBoundingClientRect().height ?? 0,
        mainHeight: main?.getBoundingClientRect().height ?? 0,
      };
    });

    expect(Math.abs(heightMetrics.rootHeight - heightMetrics.viewportHeight)).toBeLessThanOrEqual(1);
    expect(Math.abs(heightMetrics.mainHeight - heightMetrics.viewportHeight)).toBeLessThanOrEqual(1);
  });
});
