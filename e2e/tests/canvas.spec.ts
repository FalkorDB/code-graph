import { test, expect } from "@playwright/test";
import BrowserWrapper from "../infra/ui/browserWrapper";
import CodeGraph from "../logic/POM/codeGraph";
import urls from "../config/urls.json";
import { GRAPHRAG_SDK } from "../config/constants";
import { findNodeByName } from "../logic/utils";
import { nodesPath, categories, nodes } from "../config/testData";
import { ApiCalls } from "../logic/api/apiCalls";

test.describe("Canvas tests", () => {
  let browser: BrowserWrapper;

  test.beforeAll(async () => {
    browser = new BrowserWrapper();
  });

  test.afterAll(async () => {
    await browser.closeBrowser();
  });

  test(`Verify zoom in functionality on canvas`, async () => {
    const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await codeGraph.selectGraph(GRAPHRAG_SDK);
    const initialGraph = await codeGraph.getCanvasScaling();
    await codeGraph.clickZoomIn();
    await codeGraph.clickZoomIn();
    const updatedGraph = await codeGraph.getCanvasScaling();
    expect(updatedGraph.scaleX).toBeGreaterThan(initialGraph.scaleX)
    expect(updatedGraph.scaleY).toBeGreaterThan(initialGraph.scaleY)
  })

  test(`Verify zoom out functionality on canvas`, async () => {
    const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await codeGraph.selectGraph(GRAPHRAG_SDK);
    const initialGraph = await codeGraph.getCanvasScaling();
    await codeGraph.clickZoomOut();
    await codeGraph.clickZoomOut();
    const updatedGraph = await codeGraph.getCanvasScaling();
    expect(updatedGraph.scaleX).toBeLessThan(initialGraph.scaleX)
    expect(updatedGraph.scaleY).toBeLessThan(initialGraph.scaleY)
  })

  test(`Verify center graph button centers nodes in canvas`, async () => {
    const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await codeGraph.selectGraph(GRAPHRAG_SDK);
    await codeGraph.clickCenter();
    const initialGraph = await codeGraph.getCanvasScaling();
    
    await codeGraph.clickZoomOut();
    await codeGraph.clickZoomOut();
    await codeGraph.clickCenter();
    const updatedGraph = await codeGraph.getCanvasScaling();
    expect(Math.abs(initialGraph.scaleX - updatedGraph.scaleX)).toBeLessThanOrEqual(0.2);
    expect(Math.abs(initialGraph.scaleY - updatedGraph.scaleY)).toBeLessThanOrEqual(0.2);

  })

  nodes.slice(0,2).forEach((node) => {
    test(`Validate node hide functionality via element menu in canvas for ${node.nodeName}`, async () => {
      const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await codeGraph.selectGraph(GRAPHRAG_SDK);
      const initialGraph = await codeGraph.getGraphNodes();
      const targetNode = findNodeByName(initialGraph, node.nodeName);
      await codeGraph.nodeClick(targetNode.screenX, targetNode.screenY);
      await codeGraph.clickOnRemoveNodeViaElementMenu();
      const updatedGraph = await codeGraph.getGraphNodes();
      const targetNodeForUpdateGraph = findNodeByName(updatedGraph, node.nodeName);
      expect(targetNodeForUpdateGraph.visible).toBe(false);
    });
  })

  nodes.slice(0,2).forEach((node) => {
    test(`Validate unhide node functionality after hiding a node in canvas for ${node.nodeName}`, async () => {
      const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await codeGraph.selectGraph(GRAPHRAG_SDK);
      const initialGraph = await codeGraph.getGraphNodes();
      const targetNode = findNodeByName(initialGraph, node.nodeName);
      await codeGraph.nodeClick(targetNode.screenX, targetNode.screenY);
      await codeGraph.clickOnRemoveNodeViaElementMenu();
      await codeGraph.clickOnUnhideNodesBtn();
      const updatedGraph = await codeGraph.getGraphNodes();
      const targetNodeForUpdateGraph = findNodeByName(updatedGraph, node.nodeName);
      expect(targetNodeForUpdateGraph.visible).toBe(true);
    });
  })

  categories.forEach((category, index) => {
    const checkboxIndex = index + 1;
    test(`Verify that unchecking the ${category} checkbox hides ${category} nodes on the canvas`, async () => {
      const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await codeGraph.selectGraph(GRAPHRAG_SDK);
      await codeGraph.selectCodeGraphCheckbox(checkboxIndex.toString());
      const result = await codeGraph.getGraphNodes();
      const findItem = result.find((item: { category: string; }) => item.category === category);
      expect(findItem?.visible).toBe(false);
    });
  })

  nodesPath.forEach((path) => {
    test(`Verify "Clear graph" button resets canvas view for path ${path.firstNode} and ${path.secondNode}`, async () => {
      const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await codeGraph.selectGraph(GRAPHRAG_SDK);
      await codeGraph.clickOnshowPathBtn();
      await codeGraph.insertInputForShowPath("1", path.firstNode);
      await codeGraph.insertInputForShowPath("2", path.secondNode);
      const initialGraph = await codeGraph.getGraphNodes();
      const firstNode = findNodeByName(initialGraph, path.firstNode);
      const secondNode = findNodeByName(initialGraph, path.secondNode);
      expect(firstNode.isPath).toBe(true);
      expect(secondNode.isPath).toBe(true);
      await codeGraph.clickOnClearGraphBtn();
      const updateGraph = await codeGraph.getGraphNodes();
      const firstNode1 = findNodeByName(updateGraph, path.firstNode);
      const secondNode1 =  findNodeByName(updateGraph, path.secondNode);
      expect(firstNode1.isPath).toBe(false);
      expect(secondNode1.isPath).toBe(false);
    });
  })

  for (let index = 0; index < 2; index++) {
    const checkboxIndex = index + 1;
    test(`Verify selecting different graphs displays nodes in canvas - Iteration ${index + 1}`, async () => {
      const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await codeGraph.selectGraph(checkboxIndex);
      const result = await codeGraph.getGraphDetails();
      expect(result.elements.nodes.length).toBeGreaterThan(1);
      expect(result.elements.links.length).toBeGreaterThan(1);
    });
  }
  
  for (let index = 0; index < 3; index++) {
    const nodeIndex: number = index + 1;
    test(`Validate canvas node dragging for node: ${index}`, async () => {
      const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await codeGraph.selectGraph(GRAPHRAG_SDK);
      const initialGraph = await codeGraph.getGraphNodes();
      await codeGraph.changeNodePosition(initialGraph[nodeIndex].screenX, initialGraph[nodeIndex].screenY);
      const updateGraph = await codeGraph.getGraphDetails();
      expect(updateGraph.elements.nodes[nodeIndex].x).not.toBe(initialGraph[nodeIndex].x);
      expect(updateGraph.elements.nodes[nodeIndex].y).not.toBe(initialGraph[nodeIndex].y);
    });
  }

  test(`Validate node and edge counts in canvas match API data`, async () => {
    const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await codeGraph.selectGraph(GRAPHRAG_SDK);
    const { nodes, edges } = await codeGraph.getMetricsPanelInfo();
    const api = new ApiCalls();
    const response = await api.projectInfo(GRAPHRAG_SDK);
    expect(response.result.info.node_count).toEqual(parseInt(nodes));
    expect(response.result.info.edge_count).toEqual(parseInt(edges));
  });
  

  test(`Validate displayed nodes match API response after selecting a graph via UI`, async () => {
    const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await codeGraph.selectGraph(GRAPHRAG_SDK);
    const graphData = await codeGraph.getGraphDetails();
    const api = new ApiCalls();
    const response = await api.getProject(GRAPHRAG_SDK);
    const isMatching = graphData.elements.nodes.slice(0, 2).every(
      (node: any, index: number) => node.name === response.result.entities.nodes[index].properties.name
    );
    expect(isMatching).toBe(true)
  });

  nodesPath.forEach(({firstNode, secondNode}) => {
    test(`Verify successful node path connection in canvas between ${firstNode} and ${secondNode} via UI`, async () => {
      const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await codeGraph.selectGraph(GRAPHRAG_SDK);
      await codeGraph.clickOnshowPathBtn();
      await codeGraph.insertInputForShowPath("1", firstNode);
      await codeGraph.insertInputForShowPath("2", secondNode);
      const result = await codeGraph.getGraphDetails();
      const firstNodeRes = findNodeByName(result.elements.nodes, firstNode);
      const secondnodeRes = findNodeByName(result.elements.nodes, secondNode);
      expect(firstNodeRes.isPath).toBe(true)
      expect(secondnodeRes.isPath).toBe(true)
    })
  })

  nodesPath.forEach((path) => {
    test(`Validate node path connection in canvas ui and confirm via api for path ${path.firstNode} and ${path.secondNode}`, async () => {
      const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await codeGraph.selectGraph(GRAPHRAG_SDK);
      await codeGraph.clickOnshowPathBtn();
      await codeGraph.insertInputForShowPath("1", path.firstNode);
      await codeGraph.insertInputForShowPath("2", path.secondNode);
      const result = await codeGraph.getGraphDetails();
      const firstNodeRes = findNodeByName(result.elements.nodes, path.firstNode);
      const secondNodeRes = findNodeByName(result.elements.nodes, path.secondNode);
      
      const api = new ApiCalls();
      const response = await api.showPath(GRAPHRAG_SDK ,firstNodeRes.id, secondNodeRes.id);
      const callsRelationObject = response.result.paths[0].find(item => item.relation === "CALLS")
      expect(callsRelationObject?.src_node).toBe(firstNodeRes.id);
      expect(callsRelationObject?.dest_node).toBe(secondNodeRes.id);    
    });
  })
});
