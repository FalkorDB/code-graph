import { test, expect } from "@playwright/test";
import BrowserWrapper from "../infra/ui/browserWrapper";
import CodeGraph from "../logic/POM/codeGraph";
import urls from "../config/urls.json";
import { GRAPH_ID, PROJECT_CLICK, PROJECT_NAME } from "../config/constants";
import { nodes } from "../config/testData";
import { ApiCalls } from "../logic/api/apiCalls";
import { findNodeByName, findFirstNodeWithSrc } from "../logic/utils";

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
      await codeGraph.selectGraph(GRAPH_ID);
      const graphData = await codeGraph.getGraphDetails();
      const convertCoordinates = await codeGraph.transformNodeCoordinates(
        graphData
      );
      const targetNode = findNodeByName(convertCoordinates, node.nodeName);
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
      await codeGraph.selectGraph(GRAPH_ID);
      const graphData = await codeGraph.getGraphDetails();
      const convertCoordinates = await codeGraph.transformNodeCoordinates(
        graphData
      );
      const node1 = findNodeByName(convertCoordinates, node.nodeName);
      await codeGraph.nodeClick(node1.screenX, node1.screenY);
      await codeGraph.clickOnViewNode();
      await codeGraph.clickOnNodeDetailsCloseBtn();
      expect(await codeGraph.isNodeDetailsPanel()).toBe(false);
    });
  });

  nodes.forEach((node) => {
    test(`Validate node details panel header displays correct node name: ${node.nodeName}`, async () => {
      const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await browser.setPageToFullScreen();
      await codeGraph.selectGraph(GRAPH_ID);
      const graphData = await codeGraph.getGraphDetails();
      const convertCoordinates = await codeGraph.transformNodeCoordinates(
        graphData
      );
      const node1 = findNodeByName(convertCoordinates, node.nodeName);
      await codeGraph.nodeClick(node1.screenX, node1.screenY);
      expect(await codeGraph.getNodeDetailsHeader()).toContain(
        node.nodeName.toUpperCase()
      );
    });
  });

  test(`Validate copy functionality for node inside node details panel and verify with api`, async () => {
    const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await browser.setPageToFullScreen();
    await codeGraph.selectGraph(PROJECT_CLICK);
    const graphData = await codeGraph.getGraphDetails();
    const convertCoordinates = await codeGraph.transformNodeCoordinates(
      graphData
    );
    const nodeData = findFirstNodeWithSrc(convertCoordinates);
    await codeGraph.nodeClick(nodeData.screenX, nodeData.screenY);
    await codeGraph.clickOnViewNode();
    const result = await codeGraph.clickOnCopyToClipboardNodePanelDetails();
    const api = new ApiCalls();
    const response = await api.getProject(PROJECT_CLICK);
    const foundNode = response.result.entities.nodes.find(
      (nod) => nod.properties?.name === nodeData.name
    );
    expect(foundNode?.properties.src).toBe(result);
  });

  nodes.slice(0, 2).forEach((node) => {
    test(`Validate view node panel keys via api for ${node.nodeName}`, async () => {
      const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await browser.setPageToFullScreen();
      await codeGraph.selectGraph(GRAPH_ID);
      const graphData = await codeGraph.getGraphDetails();
      const convertCoordinates = await codeGraph.transformNodeCoordinates(
        graphData
      );
      const node1 = findNodeByName(convertCoordinates, node.nodeName);
      const api = new ApiCalls();
      const response = await api.getProject(PROJECT_NAME);
      const data: any = response.result.entities.nodes;
      const findNode = data.find(
        (nod: any) => nod.properties.name === node.nodeName
      );

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
