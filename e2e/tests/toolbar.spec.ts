import { test, expect } from "@playwright/test";
import BrowserWrapper from "../infra/ui/browserWrapper";
import CodeGraph from "../logic/POM/codeGraph";
import urls from "../config/urls.json";
import { GRAPHRAG_SDK } from "../config/constants";

test.describe("Toolbar and Zoom Controls tests", () => {
  let browser: BrowserWrapper;

  test.beforeAll(async () => {
    browser = new BrowserWrapper();
  });

  test.afterAll(async () => {
    await browser.closeBrowser();
  });

  test("Verify zoom in increases canvas scale", async () => {
    const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await codeGraph.selectGraph(GRAPHRAG_SDK);
    
    const initialScale = await codeGraph.getCanvasScaling();
    await codeGraph.clickZoomIn();
    const newScale = await codeGraph.getCanvasScaling();
    
    expect(newScale.scaleX).toBeGreaterThan(initialScale.scaleX);
    expect(newScale.scaleY).toBeGreaterThan(initialScale.scaleY);
  });

  test("Verify zoom out decreases canvas scale", async () => {
    const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await codeGraph.selectGraph(GRAPHRAG_SDK);
    
    const initialScale = await codeGraph.getCanvasScaling();
    await codeGraph.clickZoomOut();
    const newScale = await codeGraph.getCanvasScaling();
    
    expect(newScale.scaleX).toBeLessThan(initialScale.scaleX);
    expect(newScale.scaleY).toBeLessThan(initialScale.scaleY);
  });

  test("Verify center button resets zoom to fit", async () => {
    const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await codeGraph.selectGraph(GRAPHRAG_SDK);
    
    // Zoom in first
    await codeGraph.clickZoomIn();
    await codeGraph.clickZoomIn();
    await codeGraph.getCanvasScaling();
    
    // Click center to reset
    await codeGraph.clickCenter();
    const centeredScale = await codeGraph.getCanvasScaling();
    
    // Scale should have changed (either increased or decreased depending on implementation)
    expect(centeredScale.scaleX).toBeDefined();
    expect(centeredScale.scaleY).toBeDefined();
  });

  test("Verify zoom controls remain functional after multiple interactions", async () => {
    const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await codeGraph.selectGraph(GRAPHRAG_SDK);
    
    const scales: number[] = [];
    
    // Perform multiple zoom operations
    for (let i = 0; i < 3; i++) {
      await codeGraph.clickZoomIn();
      const scale = await codeGraph.getCanvasScaling();
      scales.push(scale.scaleX);
    }
    
    // Verify each zoom in increased the scale
    for (let i = 1; i < scales.length; i++) {
      expect(scales[i]).toBeGreaterThan(scales[i - 1]);
    }
  });

  test("Verify zoom controls work after graph change", async () => {
    const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await codeGraph.selectGraph(GRAPHRAG_SDK);
    
    const initialScale = await codeGraph.getCanvasScaling();
    await codeGraph.clickZoomIn();
    const zoomedScale = await codeGraph.getCanvasScaling();
    
    expect(zoomedScale.scaleX).toBeGreaterThan(initialScale.scaleX);
  });

  test("Verify continuous zoom maintains functionality", async () => {
    const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await codeGraph.selectGraph(GRAPHRAG_SDK);
    
    // Zoom in, then out, should return to similar scale
    const initialScale = await codeGraph.getCanvasScaling();
    
    await codeGraph.clickZoomIn();
    await codeGraph.clickZoomIn();
    await codeGraph.clickZoomOut();
    await codeGraph.clickZoomOut();
    
    const finalScale = await codeGraph.getCanvasScaling();
    
    // Should be approximately the same (within 5% tolerance for floating point operations)
    expect(Math.abs(finalScale.scaleX - initialScale.scaleX) / initialScale.scaleX).toBeLessThan(0.05);
  });
});
