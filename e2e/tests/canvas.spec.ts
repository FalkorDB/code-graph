import { test, expect } from "@playwright/test";
import BrowserWrapper from "../infra/ui/browserWrapper";
import CodeGraph from "../logic/POM/codeGraph";
import urls from "../config/urls.json";
import { GRAPH_ID, PROJECT_NAME } from "../config/constants";
import { delay, findNodeByName } from "../logic/utils";
import { nodesPath, categories, nodes, graphs } from "../config/testData";
import { ApiCalls } from "../logic/api/apiCalls";
import fs from 'fs';

test.describe("Canvas tests", () => {
  let browser: BrowserWrapper;

  test.beforeAll(async () => {
    browser = new BrowserWrapper();
  });

  test.afterAll(async () => {
    await browser.closeBrowser();
  });

  // test(`Verify zoom in functionality on canvas`, async () => {
  //   const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
  //   await codeGraph.selectGraph(GRAPH_ID);
  //   const initialGraph = await codeGraph.getCanvasScaling();
  //   await codeGraph.clickZoomIn();
  //   await codeGraph.clickZoomIn();
  //   const updatedGraph = await codeGraph.getCanvasScaling();
  //   expect(updatedGraph.scaleX).toBeGreaterThan(initialGraph.scaleX)
  //   expect(updatedGraph.scaleY).toBeGreaterThan(initialGraph.scaleY)
  // })

  // test(`Verify zoom out functionality on canvas`, async () => {
  //   const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
  //   await codeGraph.selectGraph(GRAPH_ID);
  //   const initialGraph = await codeGraph.getCanvasScaling();
  //   await codeGraph.clickZoomOut();
  //   await codeGraph.clickZoomOut();
  //   const updatedGraph = await codeGraph.getCanvasScaling();
  //   expect(updatedGraph.scaleX).toBeLessThan(initialGraph.scaleX)
  //   expect(updatedGraph.scaleY).toBeLessThan(initialGraph.scaleY)
  // })

  // test(`Verify center graph button centers nodes in canvas`, async () => {
  //   const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
  //   await codeGraph.selectGraph(GRAPH_ID);
  //   await codeGraph.clickCenter();
  //   const initialGraph = await codeGraph.getCanvasScaling();
  //   await codeGraph.clickZoomOut();
  //   await codeGraph.clickZoomOut();
  //   await codeGraph.clickCenter();
  //   const updatedGraph = await codeGraph.getCanvasScaling();
  //   expect(Math.abs(initialGraph.scaleX - updatedGraph.scaleX)).toBeLessThanOrEqual(0.1);
  //   expect(Math.abs(initialGraph.scaleY - updatedGraph.scaleY)).toBeLessThanOrEqual(0.1);
  // })

  // nodes.slice(0,2).forEach((node) => {
  //   test(`Validate node hide functionality via element menu in canvas for ${node.nodeName}`, async () => {
  //     const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
  //     await codeGraph.selectGraph(GRAPH_ID);
  //     const initialGraph = await codeGraph.getGraphDetails();
  //     const convertCoordinates = await codeGraph.transformNodeCoordinates(initialGraph);
  //     const targetNode = findNodeByName(convertCoordinates, node.nodeName);
  //     await codeGraph.nodeClick(targetNode.screenX, targetNode.screenY);
  //     await codeGraph.clickOnRemoveNodeViaElementMenu();
  //     const updatedGraph = await codeGraph.getGraphDetails();
  //     const targetNodeForUpdateGraph = findNodeByName(updatedGraph.elements.nodes, node.nodeName);
  //     expect(targetNodeForUpdateGraph.visible).toBe(false);
  //   });
  // })

  // nodes.slice(0,2).forEach((node) => {
  //   test(`Validate unhide node functionality after hiding a node in canvas for ${node.nodeName}`, async () => {
  //     const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
  //     await codeGraph.selectGraph(GRAPH_ID);
  //     const initialGraph = await codeGraph.getGraphDetails();
  //     const convertCoordinates = await codeGraph.transformNodeCoordinates(initialGraph);
  //     const targetNode = findNodeByName(convertCoordinates, node.nodeName);
  //     await codeGraph.nodeClick(targetNode.screenX, targetNode.screenY);
  //     await codeGraph.clickOnRemoveNodeViaElementMenu();
  //     await codeGraph.clickOnUnhideNodesBtn();
  //     const updatedGraph = await codeGraph.getGraphDetails();
  //     const targetNodeForUpdateGraph = findNodeByName(updatedGraph.elements.nodes, node.nodeName);
  //     expect(targetNodeForUpdateGraph.visible).toBe(true);
  //   });
  // })

  // categories.forEach((category, index) => {
  //   const checkboxIndex = index + 1;
  //   test(`Verify that unchecking the ${category} checkbox hides ${category} nodes on the canvas`, async () => {
  //     const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
  //     await codeGraph.selectGraph(GRAPH_ID);
  //     await codeGraph.selectCodeGraphCheckbox(checkboxIndex.toString());
  //     const result = await codeGraph.getGraphDetails();
  //     const findItem = result.categories.find((item: { name: string; }) => item.name === category)      
  //     expect(findItem.show).toBe(false)
  //   });
  // })

  // nodesPath.forEach((path) => {
  //   test(`Verify "Clear graph" button resets canvas view for path ${path.firstNode} and ${path.secondNode}`, async () => {
  //     const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
  //     await codeGraph.selectGraph(GRAPH_ID);
  //     await codeGraph.clickOnShowPathBtn();
  //     await codeGraph.insertInputForShowPath("1", path.firstNode);
  //     await codeGraph.insertInputForShowPath("2", path.secondNode);
  //     const initialGraph = await codeGraph.getGraphDetails();
  //     const firstNode = findNodeByName(initialGraph.elements.nodes, path.firstNode);
  //     const secondNode = findNodeByName(initialGraph.elements.nodes, path.secondNode);
  //     expect(firstNode.isPath).toBe(true);
  //     expect(secondNode.isPath).toBe(true);
  //     await codeGraph.clickOnClearGraphBtn();
  //     const updateGraph = await codeGraph.getGraphDetails();
  //     const firstNode1 = findNodeByName(updateGraph.elements.nodes, path.firstNode);
  //     const secondNode1 =  findNodeByName(updateGraph.elements.nodes, path.secondNode);
  //     expect(firstNode1.isPath).toBe(false);
  //     expect(secondNode1.isPath).toBe(false);
  //   });
  // })

  // graphs.forEach(({graphName}) => {
  //   test(`Verify selecting different graphs displays nodes in canvas - grpah: ${graphName}`, async () => {
  //     const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
  //     await codeGraph.selectGraph(graphName);
  //     const result = await codeGraph.getGraphDetails();
  //     expect(result.elements.nodes.length).toBeGreaterThan(1);
  //     expect(result.elements.links.length).toBeGreaterThan(1);
  //   });
  // })
  
  // for (let index = 0; index < 3; index++) {
  //   const nodeIndex: number = index + 1;
  //   test(`Validate canvas node dragging for node: ${index}`, async () => {
  //     const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
  //     await codeGraph.selectGraph(GRAPH_ID);
  //     const initialGraph = await codeGraph.getGraphDetails();
  //     const convertCoordinates = await codeGraph.transformNodeCoordinates(initialGraph);
  //     await codeGraph.changeNodePosition(convertCoordinates[nodeIndex].screenX, convertCoordinates[nodeIndex].screenY);
  //     const updateGraph = await codeGraph.getGraphDetails();
  //     expect(updateGraph.elements.nodes[nodeIndex].x).not.toBe(initialGraph.elements.nodes[nodeIndex].x);
  //     expect(updateGraph.elements.nodes[nodeIndex].y).not.toBe(initialGraph.elements.nodes[nodeIndex].y);
  //   });
  // }

  // test(`Validate node and edge counts in canvas match API data`, async () => {
  //   const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
  //   await codeGraph.selectGraph(GRAPH_ID);
  //   const { nodes, edges } = await codeGraph.getMetricsPanelInfo();
  //   const api = new ApiCalls();
  //   const response = await api.projectInfo(PROJECT_NAME);
  //   expect(response.result.info.node_count).toEqual(parseInt(nodes));
  //   expect(response.result.info.edge_count).toEqual(parseInt(edges));
  // });
  

  // test(`Validate displayed nodes match API response after selecting a graph via UI`, async () => {
  //   const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
  //   await codeGraph.selectGraph(GRAPH_ID);
  //   const graphData = await codeGraph.getGraphDetails();
  //   const api = new ApiCalls();
  //   const response = await api.getProject(PROJECT_NAME);
  //   const isMatching = graphData.elements.nodes.slice(0, 2).every(
  //     (node: any, index: number) => node.name === response.result.entities.nodes[index].properties.name
  //   );
  //   expect(isMatching).toBe(true)
  // });

  // nodesPath.forEach(({firstNode, secondNode}) => {
  //   test(`Verify successful node path connection in canvas between ${firstNode} and ${secondNode} via UI`, async () => {
  //     const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
  //     await codeGraph.selectGraph(GRAPH_ID);
  //     await codeGraph.clickOnShowPathBtn();
  //     await codeGraph.insertInputForShowPath("1", firstNode);
  //     await codeGraph.insertInputForShowPath("2", secondNode);
  //     const result = await codeGraph.getGraphDetails();
  //     const firstNodeRes = findNodeByName(result.elements.nodes, firstNode);
  //     const secondnodeRes = findNodeByName(result.elements.nodes, secondNode);
  //     expect(firstNodeRes.isPath).toBe(true)
  //     expect(secondnodeRes.isPath).toBe(true)
  //   })
  // })

  // nodesPath.forEach((path) => {
  //   test(`Validate node path connection in canvas ui and confirm via api for path ${path.firstNode} and ${path.secondNode}`, async () => {
  //     const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
  //     await codeGraph.selectGraph(GRAPH_ID);
  //     await codeGraph.clickOnShowPathBtn();
  //     await codeGraph.insertInputForShowPath("1", path.firstNode);
  //     await codeGraph.insertInputForShowPath("2", path.secondNode);
  //     const result = await codeGraph.getGraphDetails();
  //     const firstNodeRes = findNodeByName(result.elements.nodes, path.firstNode);
  //     const secondNodeRes = findNodeByName(result.elements.nodes, path.secondNode);
      
  //     const api = new ApiCalls();
  //     const response = await api.showPath(PROJECT_NAME ,firstNodeRes.id, secondNodeRes.id);
  //     const callsRelationObject = response.result.paths[0].find(item => item.relation === "CALLS")
  //     expect(callsRelationObject?.src_node).toBe(firstNodeRes.id);
  //     expect(callsRelationObject?.dest_node).toBe(secondNodeRes.id);    
  //   });
  // })

  // test(`Verify file download is triggered and saved after clicking download`, async () => {
  //   const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
  //   await codeGraph.selectGraph(GRAPH_ID);
  //   const download = await codeGraph.downloadImage();
  //   const downloadPath = await download.path();
  //   expect(fs.existsSync(downloadPath)).toBe(true);
  // })

  nodes.slice(1,4).forEach((node) => {
    test(`Verify tooltip appears when hovering over node: ${node.nodeName}`, async () => {
      const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await browser.setPageToFullScreen();
      await codeGraph.selectGraph(GRAPH_ID);
      await codeGraph.getGraphDetails();
      await codeGraph.fillSearchBar(node.nodeName);
      await codeGraph.selectSearchBarOptionBtn("1");
      await delay(2000);
      await codeGraph.hoverAtCanvasCenter();
      expect(await codeGraph.isNodeToolTipVisible()).toBe(true);
    })
  })
  
});
