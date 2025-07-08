import { test, expect } from "@playwright/test";
import BrowserWrapper from "../infra/ui/browserWrapper";
import CodeGraph from "../logic/POM/codeGraph";
import urls from "../config/urls.json";
import { FLASK_GRAPH, GRAPHRAG_SDK } from "../config/constants";
import { findNodeByName, findFirstNodeWithSrc, findNodeWithSpecificSrc } from "../logic/utils";
import { nodes } from "../config/testData";
import { ApiCalls } from "../logic/api/apiCalls";

test.describe("Node details panel tests", () => {
  let browser: BrowserWrapper;

  test.beforeAll(async () => {
    browser = new BrowserWrapper();
  });

  test.afterAll(async () => {
    await browser.closeBrowser();
  });

  nodes.slice(0,2).forEach((node) => {
    test(`Validate node details panel displayed on node click for ${node.nodeName}`, async () => {
      const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await browser.setPageToFullScreen();
      await codeGraph.selectGraph(GRAPHRAG_SDK);
      const graphData = await codeGraph.getGraphNodes();
      const targetNode = findNodeByName(graphData, node.nodeName);
      await codeGraph.nodeClick(targetNode.screenX, targetNode.screenY);
      await codeGraph.clickOnViewNode();
      expect(await codeGraph.isNodeDetailsPanel()).toBe(true)
    })
  })

  nodes.slice(0,2).forEach((node) => {
    test(`Validate node details panel is not displayed after close interaction for ${node.nodeName}`, async () => {
      const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await browser.setPageToFullScreen();
      await codeGraph.selectGraph(GRAPHRAG_SDK);
      const graphData = await codeGraph.getGraphNodes();
      const targetNode = findNodeByName(graphData, node.nodeName);
      await codeGraph.nodeClick(targetNode.screenX, targetNode.screenY);
      await codeGraph.clickOnViewNode();
      await codeGraph.clickOnNodeDetailsCloseBtn();
      expect(await codeGraph.isNodeDetailsPanel()).toBe(false)
    })
  })

  nodes.forEach((node) => {
    test(`Validate node details panel header displays correct node name: ${node.nodeName}`, async () => {
      const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await browser.setPageToFullScreen();
      await codeGraph.selectGraph(GRAPHRAG_SDK);
      const graphData = await codeGraph.getGraphNodes();
      const targetNode = findNodeByName(graphData, node.nodeName);
      await codeGraph.nodeClick(targetNode.screenX, targetNode.screenY);
      expect(await codeGraph.getNodeDetailsHeader()).toContain(node.nodeName.toUpperCase())
    })
  })
  

  test.only(`Validate copy functionality for node inside node details panel and verify with api`, async () => {
    const api = new ApiCalls();
    const response = await api.getProject(FLASK_GRAPH);

    const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await browser.setPageToFullScreen();
    await codeGraph.selectGraph(FLASK_GRAPH);
    const graphData = await codeGraph.getGraphNodes();
    const targetNode = findNodeWithSpecificSrc(graphData, "test_options_work");

    await new Promise(resolve => setTimeout(resolve, 2000));
    await codeGraph.nodeClick(targetNode.screenX, targetNode.screenY);
    await codeGraph.clickOnViewNode();
    const result = await codeGraph.clickOnCopyToClipboardNodePanelDetails();      

    const foundNode = response.result.entities.nodes.find((nod) => nod.properties?.name === targetNode.name);
    expect(foundNode?.properties.src).toBe(result);
  });

  nodes.slice(0, 2).forEach((node) => {
    test(`Validate view node panel keys via api for ${node.nodeName}`, async () => {
      const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await browser.setPageToFullScreen();
      await codeGraph.selectGraph(GRAPHRAG_SDK);
      const graphData = await codeGraph.getGraphNodes();
      const node1 = findNodeByName(graphData, node.nodeName);
      const api = new ApiCalls();
      const response = await api.getProject(GRAPHRAG_SDK);
      const data: any = response.result.entities.nodes;
      const findNode = data.find((nod: any) => nod.properties.name === node.nodeName);
      await codeGraph.nodeClick(node1.screenX, node1.screenY);
      let elements = await codeGraph.getNodeDetailsPanelElements();
      elements.splice(2, 1);
      const apiFields = [
        ...Object.keys(findNode),
        ...Object.keys(findNode.properties || {}),
      ];

      const isValid = elements.every((field) => {
        const cleanedField = field.replace(":", "").trim();
        return apiFields.includes(cleanedField);
      });
      expect(isValid).toBe(true);
    });
  });
});