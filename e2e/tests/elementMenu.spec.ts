import { test, expect } from "@playwright/test";
import BrowserWrapper from "../infra/ui/browserWrapper";
import CodeGraph from "../logic/POM/codeGraph";
import urls from "../config/urls.json";
import { GRAPHRAG_SDK } from "../config/constants";
import { findNodeByName } from "../logic/utils";
import { nodes } from "../config/testData";

test.describe("Element Menu and Right-click Menu tests", () => {
  let browser: BrowserWrapper;

  test.beforeAll(async () => {
    browser = new BrowserWrapper();
  });

  test.afterAll(async () => {
    await browser.closeBrowser();
  });

  test("Verify element menu appears on right-click at canvas center", async () => {
    const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await codeGraph.selectGraph(GRAPHRAG_SDK);
    await codeGraph.rightClickAtCanvasCenter();
    const isMenuVisible = await codeGraph.isElementMenuVisible();
    expect(isMenuVisible).toBe(true);
  });

  test("Verify element menu has consistent positioning gap from node", async () => {
    const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await browser.setPageToFullScreen();
    await codeGraph.selectGraph(GRAPHRAG_SDK);
    
    // Get a node's position
    const graphData = await codeGraph.getGraphNodes();
    const targetNode = findNodeByName(graphData, nodes[0].nodeName);
    expect(targetNode).toBeDefined();
    
    // Right-click on the node to trigger element menu
    await codeGraph.nodeClick(targetNode.screenX, targetNode.screenY);
    await codeGraph.rightClickAtNode(targetNode.screenX, targetNode.screenY);
    
    // Verify menu is visible
    const isMenuVisible = await codeGraph.isElementMenuVisible();
    expect(isMenuVisible).toBe(true);
    
    // Get menu position and verify it appears below the node (not overlapping)
    const menuBox = await codeGraph.getElementMenuBoundingBox();
    expect(menuBox).toBeDefined();
    expect(menuBox.y).toBeGreaterThan(targetNode.screenY);
  });

  test("Verify element menu contains 'View Node' button", async () => {
    const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await codeGraph.selectGraph(GRAPHRAG_SDK);
    await codeGraph.rightClickAtCanvasCenter();
    
    const hasViewNodeBtn = await codeGraph.hasElementMenuButton("View Node");
    expect(hasViewNodeBtn).toBe(true);
  });

  test("Verify element menu 'View Node' button opens node details panel", async () => {
    const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await browser.setPageToFullScreen();
    await codeGraph.selectGraph(GRAPHRAG_SDK);
    
    // Get a node and right-click on it
    const graphData = await codeGraph.getGraphNodes();
    const targetNode = findNodeByName(graphData, nodes[0].nodeName);
    expect(targetNode).toBeDefined();
    
    await codeGraph.rightClickAtNode(targetNode.screenX, targetNode.screenY);
    await codeGraph.clickOnViewNode();
    
    expect(await codeGraph.isNodeDetailsPanel()).toBe(true);
  });

  test("Verify element menu 'Remove' button removes node/link from canvas", async () => {
    const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await browser.setPageToFullScreen();
    await codeGraph.selectGraph(GRAPHRAG_SDK);
    
    // Get initial node count
    const initialGraphData = await codeGraph.getGraphNodes();
    const initialNodeCount = initialGraphData.length;
    
    // Right-click at canvas center and remove
    await codeGraph.rightClickAtCanvasCenter();
    await codeGraph.clickOnRemoveNodeViaElementMenu();
    
    // Wait for animation and verify node count decreased
    await codeGraph.waitForCanvasAnimationToEnd();
    const updatedGraphData = await codeGraph.getGraphNodes();
    expect(updatedGraphData.length).toBeLessThan(initialNodeCount);
  });

  test("Verify element menu positioning respects canvas boundaries", async () => {
    const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await browser.setPageToFullScreen();
    await codeGraph.selectGraph(GRAPHRAG_SDK);
    
    // Right-click at canvas center
    await codeGraph.rightClickAtCanvasCenter();
    
    // Get menu bounding box and canvas bounds
    const menuBox = await codeGraph.getElementMenuBoundingBox();
    const canvasBox = await codeGraph.getCanvasBoundingBox();
    
    // Verify menu stays within canvas bounds
    expect(menuBox.x).toBeGreaterThanOrEqual(canvasBox.x);
    expect(menuBox.y + menuBox.height).toBeLessThanOrEqual(canvasBox.y + canvasBox.height);
  });
});
