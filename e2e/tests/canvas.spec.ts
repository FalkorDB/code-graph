import { test, expect } from "@playwright/test";
import BrowserWrapper from "../infra/ui/browserWrapper";
import CodeGraph from "../logic/POM/codeGraph";
import urls from "../config/urls.json";
import { GRAPHRAG_SDK } from "../config/constants";
import { findNodeByName } from "../logic/utils";
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

  test(`Verify zoom in functionality on canvas`, async () => {
    const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await codeGraph.selectGraph(GRAPHRAG_SDK);
    const initialGraph = await codeGraph.getCanvasScaling();
    await codeGraph.clickZoomIn();
    await codeGraph.clickZoomIn();
    await codeGraph.waitForCanvasAnimationToEnd();
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
    await codeGraph.waitForCanvasAnimationToEnd();
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
    await codeGraph.waitForCanvasAnimationToEnd();
    const updatedGraph = await codeGraph.getCanvasScaling();
    expect(Math.abs(initialGraph.scaleX - updatedGraph.scaleX)).toBeLessThanOrEqual(0.5);
    expect(Math.abs(initialGraph.scaleY - updatedGraph.scaleY)).toBeLessThanOrEqual(0.5);

  })

  test(`Validate node hide functionality via element menu in canvas for ${nodes[0].nodeName}`, async () => {
    const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await browser.setPageToFullScreen();
    await codeGraph.selectGraph(GRAPHRAG_SDK);
    await codeGraph.fillSearchBar(nodes[0].nodeName);
    await codeGraph.selectSearchBarOptionBtn("1");
    await codeGraph.waitForCanvasAnimationToEnd();
    const initialGraph = await codeGraph.getGraphNodes();
    const targetNode = findNodeByName(initialGraph, nodes[0].nodeName);
    expect(targetNode).toBeDefined();
    await codeGraph.nodeClick(targetNode.screenX, targetNode.screenY);
    await codeGraph.clickOnRemoveNodeViaElementMenu();
    const updatedGraph = await codeGraph.getGraphNodes();
    const updatedNode = findNodeByName(updatedGraph, nodes[0].nodeName);
    expect(updatedNode).toBeDefined();
    expect(updatedNode.visible).toBe(false);
  });

  test(`Validate unhide node functionality after hiding a node in canvas for ${nodes[0].nodeName}`, async () => {
    const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await browser.setPageToFullScreen();
    await codeGraph.selectGraph(GRAPHRAG_SDK);
    await codeGraph.fillSearchBar(nodes[0].nodeName);
    await codeGraph.selectSearchBarOptionBtn("1");
    await codeGraph.waitForCanvasAnimationToEnd();
    await codeGraph.rightClickAtCanvasCenter();
    await codeGraph.clickOnRemoveNodeViaElementMenu();
    await codeGraph.clickOnUnhideNodesBtn();
    const updatedGraph = await codeGraph.getGraphNodes();
    const targetNodeForUpdateGraph = findNodeByName(updatedGraph, nodes[0].nodeName);
    expect(targetNodeForUpdateGraph.visible).toBe(true);
  });

  categories.forEach((category, index) => {
    const checkboxIndex = index + 1;
    test(`Verify that unchecking the ${category} checkbox hides ${category} nodes on the canvas`, async () => {
      const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await codeGraph.selectGraph(GRAPHRAG_SDK);
      await codeGraph.selectCodeGraphCheckbox(checkboxIndex.toString());
      const result = await codeGraph.getGraphNodes();
      const findItem = result.find((item: { category: string; }) => item.category === category);
      expect(findItem.visible).toBeFalsy();
    });
  })

  nodesPath.forEach((path) => {
    test(`Verify "Clear graph" button resets canvas view for path ${path.firstNode} and ${path.secondNode}`, async () => {
      const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await browser.setPageToFullScreen();
      await codeGraph.selectGraph(GRAPHRAG_SDK);
      await codeGraph.clickOnShowPathBtn("Show the path");
      await codeGraph.fillPathInputsAndWait(path.firstNode, path.secondNode);
      const initialGraph = await codeGraph.getGraphNodes();
      const firstNode = findNodeByName(initialGraph, path.firstNode);
      const secondNode = findNodeByName(initialGraph, path.secondNode);
      expect(firstNode).toBeDefined();
      expect(secondNode).toBeDefined();
      await codeGraph.clickOnClearGraphBtn();
      const updateGraph = await codeGraph.getGraphNodes();
      expect(updateGraph.length).toBeGreaterThan(0);
      const firstNodeAfter = findNodeByName(updateGraph, path.firstNode);
      const secondNodeAfter = findNodeByName(updateGraph, path.secondNode);
      expect(firstNodeAfter).toBeDefined();
      expect(firstNodeAfter.isPath).toBeFalsy();
      expect(secondNodeAfter).toBeDefined();
      expect(secondNodeAfter.isPath).toBeFalsy();
    });
  })

  graphs.forEach(({graphName}) => {
    test(`Verify selecting different graphs displays nodes in canvas - graph: ${graphName}`, async () => {
      const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await codeGraph.selectGraph(graphName);
      const result = await codeGraph.getGraphDetails();
      const nodes = result.elements?.nodes || result.nodes;
      const links = result.elements?.links || result.links;
      expect(nodes.length).toBeGreaterThan(1);
      expect(links.length).toBeGreaterThan(1);
    });
  })

  for (let index = 1; index < 3; index++) {
    const nodeIndex: number = index + 1;
    test(`Validate canvas node dragging for node: ${index}`, async () => {
      const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await browser.setPageToFullScreen();
      await codeGraph.selectGraph(GRAPHRAG_SDK);
      const initialGraph = await codeGraph.getGraphNodes();
      const nodeName = initialGraph[nodeIndex].name || initialGraph[nodeIndex].data?.name;
      await codeGraph.fillSearchBar(nodeName);
      await codeGraph.selectSearchBarOptionBtn("1");
      await codeGraph.waitForCanvasAnimationToEnd();
      const updatedGraph = await codeGraph.getGraphNodes();
      const targetNode = findNodeByName(updatedGraph, nodeName);
      const initialX = targetNode.x;
      const initialY = targetNode.y;
      await codeGraph.dragFromCanvasCenter();
      const updateGraph = await codeGraph.getGraphDetails();
      const nodes = updateGraph.elements?.nodes || updateGraph.nodes;
      const draggedNode = findNodeByName(nodes, nodeName);

      expect(draggedNode.x).not.toBe(initialX);
      expect(draggedNode.y).not.toBe(initialY);
    });
  }

  test(`Validate node and edge counts in canvas match API data`, async () => {
    const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await codeGraph.selectGraph(GRAPHRAG_SDK);
    const { nodes, edges } = await codeGraph.getMetricsPanelInfo();
    const api = new ApiCalls();
    const response = await api.projectInfo(GRAPHRAG_SDK);
    expect(response.info.node_count).toEqual(parseInt(nodes));
    expect(response.info.edge_count).toEqual(parseInt(edges));
  });
  

  test(`Validate displayed nodes match API response after selecting a graph via UI`, async () => {
    const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await codeGraph.selectGraph(GRAPHRAG_SDK);
    const graphData = await codeGraph.getGraphDetails();
    const api = new ApiCalls();
    const response = await api.getProject(GRAPHRAG_SDK);
    const nodes = graphData.elements?.nodes || graphData.nodes;
    const isMatching = nodes.slice(0, 2).every(
      (node: any, index: number) => {
        const nodeName = node.name || node.data?.name;
        return nodeName === response.entities.nodes[index].properties.name;
      }
    );
    expect(isMatching).toBe(true)
  });

  nodesPath.forEach(({firstNode, secondNode}) => {
    test(`Verify successful node path connection in canvas between ${firstNode} and ${secondNode} via UI`, async () => {
      const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await codeGraph.selectGraph(GRAPHRAG_SDK);
      await codeGraph.clickOnShowPathBtn("Show the path");
      await codeGraph.fillPathInputsAndWait(firstNode, secondNode);
      const result = await codeGraph.getGraphNodes();
      const firstNodeRes = findNodeByName(result, firstNode);
      
      const secondnodeRes = findNodeByName(result, secondNode);
      expect(firstNodeRes).toBeDefined();
      expect(secondnodeRes).toBeDefined();
    })
  })

  nodesPath.forEach((path) => {
    test(`Validate node path connection in canvas ui and confirm via api for path ${path.firstNode} and ${path.secondNode}`, async () => {
      const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await codeGraph.selectGraph(GRAPHRAG_SDK);
      await codeGraph.clickOnShowPathBtn("Show the path");
      await codeGraph.fillPathInputsAndWait(path.firstNode, path.secondNode);
      const result = await codeGraph.getGraphDetails();
      const nodes = result.elements?.nodes || result.nodes;
      const firstNodeRes = findNodeByName(nodes, path.firstNode);
      const secondNodeRes = findNodeByName(nodes, path.secondNode);

      expect(firstNodeRes).toBeDefined();
      expect(secondNodeRes).toBeDefined();

      const api = new ApiCalls();
      const response = await api.showPath(GRAPHRAG_SDK ,firstNodeRes!.id, secondNodeRes!.id);
      const callsRelationObject = response.paths[0].find(item => item.relation === "CALLS")
      expect(callsRelationObject?.src_node).toBe(firstNodeRes!.id);
      expect(callsRelationObject?.dest_node).toBe(secondNodeRes!.id);
    });
  })

  test(`Verify file download is triggered and saved after clicking download`, async () => {
    const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await codeGraph.selectGraph(GRAPHRAG_SDK);
    const download = await codeGraph.downloadImage();
    const downloadPath = await download.path();
    expect(fs.existsSync(downloadPath)).toBe(true);
  })

  nodes.forEach((node) => {
    test(`Verify tooltip appears when hovering over node: ${node.nodeName}`, async () => {
      const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await browser.setPageToFullScreen();
      await codeGraph.selectGraph(GRAPHRAG_SDK);
      await codeGraph.getGraphDetails();
      await codeGraph.fillSearchBar(node.nodeName);
      await codeGraph.selectSearchBarOptionBtn("1");
      await codeGraph.waitForCanvasAnimationToEnd();
      await codeGraph.hoverAtCanvasCenter();
      expect(await codeGraph.isNodeToolTipVisible(node.nodeName)).toBe(true);
    })
  })

  // --- Tests covering the convertToCanvasData visibility fix ---
  // Previously, invisible nodes were filtered out before being sent to the canvas,
  // which caused them to be fully removed (losing their positions). Now all nodes
  // are sent with their `visible` property so the canvas preserves their positions.

  test(`Validate hidden node remains in canvas data with visible=false after remove`, async () => {
    const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await browser.setPageToFullScreen();
    await codeGraph.selectGraph(GRAPHRAG_SDK);
    await codeGraph.fillSearchBar(nodes[0].nodeName);
    await codeGraph.selectSearchBarOptionBtn("1");
    await codeGraph.waitForCanvasAnimationToEnd();
    const initialGraph = await codeGraph.getGraphNodes();
    const targetNode = findNodeByName(initialGraph, nodes[0].nodeName);
    expect(targetNode).toBeDefined();

    // Hide the node via the element menu
    await codeGraph.nodeClick(targetNode.screenX, targetNode.screenY);
    await codeGraph.clickOnRemoveNodeViaElementMenu();

    const updatedGraph = await codeGraph.getGraphNodes();
    const hiddenNode = findNodeByName(updatedGraph, nodes[0].nodeName);

    // Node must still be present in canvas data (not removed), just invisible
    expect(hiddenNode).toBeDefined();
    expect(hiddenNode.visible).toBe(false);
  });

  test(`Validate node position is preserved after hide and unhide for ${nodes[0].nodeName}`, async () => {
    const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await browser.setPageToFullScreen();
    await codeGraph.selectGraph(GRAPHRAG_SDK);
    await codeGraph.fillSearchBar(nodes[0].nodeName);
    await codeGraph.selectSearchBarOptionBtn("1");
    await codeGraph.waitForCanvasAnimationToEnd();

    // Capture position before hiding
    const initialGraph = await codeGraph.getGraphNodes();
    const initialNode = findNodeByName(initialGraph, nodes[0].nodeName);
    expect(initialNode).toBeDefined();
    const { x: xBefore, y: yBefore } = initialNode;

    // Hide the node
    await codeGraph.nodeClick(initialNode.screenX, initialNode.screenY);
    await codeGraph.clickOnRemoveNodeViaElementMenu();

    // Unhide all nodes — no simulation reruns, so positions must be preserved
    await codeGraph.clickOnUnhideNodesBtn();

    const updatedGraph = await codeGraph.getGraphNodes();
    const restoredNode = findNodeByName(updatedGraph, nodes[0].nodeName);
    expect(restoredNode).toBeDefined();
    expect(restoredNode.visible).toBe(true);

    // Position tolerance of 1 unit accounts for floating-point serialisation
    expect(Math.abs(restoredNode.x - xBefore)).toBeLessThan(1);
    expect(Math.abs(restoredNode.y - yBefore)).toBeLessThan(1);
  });

  test(`Validate category node positions are preserved after toggling visibility for ${categories[0]}`, async () => {
    const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await codeGraph.selectGraph(GRAPHRAG_SDK);
    await codeGraph.waitForCanvasAnimationToEnd();

    // Capture positions of the first visible category node before hiding
    const initialGraph = await codeGraph.getGraphNodes();
    const categoryNodesBefore = initialGraph.filter((n: any) => n.category === categories[0]);
    expect(categoryNodesBefore.length).toBeGreaterThan(0);
    const sampleNode = categoryNodesBefore[0];
    const { x: xBefore, y: yBefore } = sampleNode;

    // Hide the category (checkbox 1 = categories[0])
    await codeGraph.selectCodeGraphCheckbox("1");

    // Show the category again — canvas must not re-simulate; positions are kept
    await codeGraph.selectCodeGraphCheckbox("1");

    const updatedGraph = await codeGraph.getGraphNodes();
    const restoredNode = updatedGraph.find((n: any) => n.id === sampleNode.id);
    expect(restoredNode).toBeDefined();
    expect(restoredNode.visible).toBe(true);

    expect(Math.abs(restoredNode.x - xBefore)).toBeLessThan(1);
    expect(Math.abs(restoredNode.y - yBefore)).toBeLessThan(1);
  });

});
