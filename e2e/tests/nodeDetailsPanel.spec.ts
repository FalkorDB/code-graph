import { test, expect } from "@playwright/test";
import BrowserWrapper from "../infra/ui/browserWrapper";
import CodeGraph from "../logic/POM/codeGraph";
import urls from "../config/urls.json";
import { FLASK_GRAPH, GRAPHRAG_SDK } from "../config/constants";
import { findNodeByName } from "../logic/utils";
import { nodes } from "../config/testData";


test.describe("Node details panel tests", () => {
  let browser: BrowserWrapper;

  test.beforeAll(async () => {
    browser = new BrowserWrapper();
  });

  test.afterAll(async () => {
    await browser.closeBrowser();
  });

  nodes.slice(0, 2).forEach((node) => {
    test(`Validate node details panel displayed on node click for ${node.nodeName}`, async () => {
      const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await browser.setPageToFullScreen();
      await codeGraph.selectGraph(GRAPHRAG_SDK);
      await codeGraph.fillSearchBar(node.nodeName);
      await codeGraph.selectSearchBarOptionBtn("1");
      await codeGraph.waitForCanvasAnimationToEnd();
      const graphData = await codeGraph.getGraphNodes();

      const targetNode = findNodeByName(graphData, node.nodeName);
      expect(targetNode).toBeDefined();
      await codeGraph.nodeClick(targetNode.screenX, targetNode.screenY);
      await codeGraph.clickOnViewNode();
      expect(await codeGraph.isNodeDetailsPanel()).toBe(true);
    });
  });

  nodes.slice(0, 2).forEach((node) => {
    test(`Validate node details panel is not displayed after close interaction for ${node.nodeName}`, async () => {
      const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await browser.setPageToFullScreen();
      await codeGraph.selectGraph(GRAPHRAG_SDK);
      await codeGraph.fillSearchBar(node.nodeName);
      await codeGraph.selectSearchBarOptionBtn("1");
      await codeGraph.waitForCanvasAnimationToEnd();
      const graphData = await codeGraph.getGraphNodes();
      const targetNode = findNodeByName(graphData, node.nodeName);
      await codeGraph.nodeClick(targetNode.screenX, targetNode.screenY);
      await codeGraph.clickOnViewNode();
      await codeGraph.clickOnNodeDetailsCloseBtn();
      expect(await codeGraph.isNodeDetailsPanel()).toBe(false);
    });
  });

  nodes.forEach((node) => {
    test(`Validate node details panel header displays correct node name: ${node.nodeName}`, async () => {
      const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await browser.setPageToFullScreen();
      await codeGraph.selectGraph(GRAPHRAG_SDK);
      await codeGraph.fillSearchBar(node.nodeName);
      await codeGraph.selectSearchBarOptionBtn("1");
      await codeGraph.waitForCanvasAnimationToEnd();
      const graphData = await codeGraph.getGraphNodes();
      const targetNode = findNodeByName(graphData, node.nodeName);
      await codeGraph.nodeClick(targetNode.screenX, targetNode.screenY);
      expect(await codeGraph.getNodeDetailsHeader()).toContain(node.nodeName.toUpperCase())
    })
  })
  

  test(`Validate copy functionality for node inside node details panel and verify with api`, async () => {
    const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await browser.setPageToFullScreen();
    await codeGraph.selectGraph(FLASK_GRAPH);
    const graphData = await codeGraph.getGraphNodes();
    const targetNode = graphData.find(node => node.src) || graphData[0];
    const nodeName = targetNode.name || targetNode.data?.name;
    await codeGraph.fillSearchBar(nodeName);
    await codeGraph.selectSearchBarOptionBtn("1");
    await codeGraph.waitForCanvasAnimationToEnd();

    await codeGraph.rightClickAtCanvasCenter();
    await codeGraph.clickOnViewNode();
    const copiedText = await codeGraph.clickOnCopyToClipboardNodePanelDetails();
    expect(copiedText).toBe(targetNode.src || "");
});

  const expectedNodeKeys = ["id", "doc", "name", "path", "src_end", "src_start"];

  nodes.slice(0, 2).forEach((node) => {
    test(`Validate node data contains expected properties for ${node.nodeName}`, async () => {
      const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await browser.setPageToFullScreen();
      await codeGraph.selectGraph(GRAPHRAG_SDK);
      await codeGraph.fillSearchBar(node.nodeName);
      await codeGraph.selectSearchBarOptionBtn("1");
      await codeGraph.waitForCanvasAnimationToEnd();
      const graphData = await codeGraph.getGraphNodes();
      const targetNode = findNodeByName(graphData, node.nodeName);
      expect(targetNode).toBeDefined();

      for (const key of expectedNodeKeys) {
        expect(targetNode).toHaveProperty(key);
      }
    });
  });
});
