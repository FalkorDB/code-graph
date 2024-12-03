import { test, expect } from "@playwright/test";
import BrowserWrapper from "../infra/ui/browserWrapper";
import CodeGraph from "../logic/POM/codeGraph";
import urls from "../config/urls.json";
import { GRAPH_ID, Node_Add_Edge, Node_Import_Data } from "../config/constants";
import { delay } from "../logic/utils";
import { searchData, specialCharacters } from "../config/testData";
import { CanvasAnalysisResult } from "../logic/canvasAnalysis";

const colors: (keyof CanvasAnalysisResult)[] = ["red", "yellow", "green"];

test.describe("Code graph tests", () => {
  let browser: BrowserWrapper;

  test.beforeAll(async () => {
    browser = new BrowserWrapper();
  });

  test.afterAll(async () => {
    await browser.closeBrowser();
  });

  searchData.slice(0, 2).forEach(({ searchInput }) => {
    test(`Verify search bar auto-complete behavior for input: ${searchInput} via UI`, async () => {
      const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await codeGraph.selectGraph(GRAPH_ID);
      await codeGraph.fillSearchBar(searchInput);
      await delay(1000);
      const textList = await codeGraph.getSearchBarElementsText();
      textList.forEach((text) => {
        expect(text.toLowerCase()).toContain(searchInput);
      });
    });
  });

  searchData.slice(2, 4).forEach(({ searchInput, completedSearchInput }) => {
    test(`Validate search bar updates with selected element: ${searchInput}`, async () => {
      const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await codeGraph.selectGraph(GRAPH_ID);
      await codeGraph.fillSearchBar(searchInput);
      await delay(1000);
      await codeGraph.selectSearchBarOptionBtn("1");
      expect(await codeGraph.getSearchBarInputValue()).toBe(
        completedSearchInput
      );
    });
  });

  searchData.slice(0, 2).forEach(({ searchInput }) => {
    test(`Verify auto-scroll scroll in search bar list for: ${searchInput}`, async () => {
      const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await codeGraph.selectGraph(GRAPH_ID);
      await codeGraph.fillSearchBar(searchInput);
      await codeGraph.scrollToBottomInSearchBarList();
      expect(await codeGraph.isScrolledToBottomInSearchBarList()).toBe(true);
    });
  });

  specialCharacters.forEach(({ character, expectedRes }) => {
    test(`Verify entering special characters behavior in search bar for: ${character}`, async () => {
      const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await codeGraph.selectGraph(GRAPH_ID);
      await codeGraph.fillSearchBar(character);
      await delay(1000);
      expect((await codeGraph.getSearchBarInputValue()).includes(character)).toBe(expectedRes);
    });
  });

  test(`Verify zoom in functionality on canvas`, async () => {
    const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await codeGraph.selectGraph(GRAPH_ID);
    const initialNodeAnalysis = await codeGraph.getCanvasAnalysis();
    await codeGraph.clickZoomIn();
    await codeGraph.clickZoomIn();
    const updatedNodeAnalysis = await codeGraph.getCanvasAnalysis();
    for (const color of colors) {
      const initialRadius = initialNodeAnalysis[color][0].radius;
      const updatedRadius = updatedNodeAnalysis[color][0].radius;
      expect(initialRadius).toBeDefined();
      expect(updatedRadius).toBeDefined();
      expect(updatedRadius).toBeGreaterThan(initialRadius);
    }
  })

  test(`Verify zoom out functionality on canvas`, async () => {
    const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await codeGraph.selectGraph(GRAPH_ID);
    const initialNodeAnalysis = await codeGraph.getCanvasAnalysis();
    for (let i = 0; i < 5; i++) {
      await codeGraph.clickZoomOut();
    }
    const updatedNodeAnalysis = await codeGraph.getCanvasAnalysis();
    for (const color of colors) {
      const initialRadius = initialNodeAnalysis[color][0].radius;
      const updatedRadius = updatedNodeAnalysis[color][0].radius;
      expect(initialRadius).toBeDefined();
      expect(updatedRadius).toBeDefined();
      expect(updatedRadius).toBeLessThan(initialRadius);
    }
  })

  test(`Verify center graph button centers nodes in canvas`, async () => {
    const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await codeGraph.selectGraph(GRAPH_ID);
    const initialNodeAnalysis = await codeGraph.getCanvasAnalysis();
    await codeGraph.clickZoomIn();
    await codeGraph.clickZoomIn();
    await codeGraph.clickCenter();
    const updatedNodeAnalysis = await codeGraph.getCanvasAnalysis();
    for (const color of colors) {
      const initialRadius = Math.round(initialNodeAnalysis[color][0].radius);
      const updatedRadius = Math.round(updatedNodeAnalysis[color][0].radius);
      expect(initialRadius).toBeDefined();
      expect(updatedRadius).toBeDefined();
      expect(updatedRadius).toBeCloseTo(initialRadius);
    }
  })

  test(`Validate node removal functionality via element menu in canvas`, async () => {
    const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await codeGraph.selectGraph(GRAPH_ID);
    const initialNodeAnalysis = await codeGraph.getCanvasAnalysis();
    await codeGraph.rightClickOnNode(initialNodeAnalysis.red[0].x, initialNodeAnalysis.red[0].y);
    await codeGraph.clickOnRemoveNodeViaElementMenu();
    const updatedNodeAnalysis = await codeGraph.getCanvasAnalysis();
    expect(initialNodeAnalysis.red.length).toBeGreaterThan(updatedNodeAnalysis.red.length);
  });

  colors.forEach((color, index) => {
    const checkboxIndex = index + 1;
    test(`Verify that unchecking the ${color} checkbox hides ${color} nodes on the canvas`, async () => {
      const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await codeGraph.selectGraph(GRAPH_ID);
      await codeGraph.selectCodeGraphCheckbox(checkboxIndex.toString());
      const result = await codeGraph.getCanvasAnalysis();
      expect(result[color].length).toBe(0);
    });
  })

  test(`Verify "Clear graph" button resets canvas view`, async () => {
    const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await codeGraph.selectGraph(GRAPH_ID);
    const initialAnalysis = await codeGraph.getCanvasAnalysis();
    const initialNodeCount = initialAnalysis.green.length + initialAnalysis.yellow.length + initialAnalysis.red.length;
    await codeGraph.clickOnshowPathBtn();
    await codeGraph.insertInputForShowPath("1", Node_Import_Data);
    await codeGraph.insertInputForShowPath("2", Node_Add_Edge);
    await codeGraph.clickOnClearGraphBtn();
    const finalAnalysis = await codeGraph.getCanvasAnalysis();
    const finalNodeCount = finalAnalysis.green.length + finalAnalysis.yellow.length + finalAnalysis.red.length;
    expect(initialNodeCount).toBe(finalNodeCount);
  });

  for (let index = 0; index < 3; index++) {
    const checkboxIndex = index + 1;
    test(`Verify selecting different graphs displays nodes in canvas - Iteration ${index + 1}`, async () => {
      const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await codeGraph.selectGraph(checkboxIndex.toString());
      const result = await codeGraph.getCanvasAnalysis();
      const nodesLength = result.green.length + result.yellow.length + result.red.length;
      expect(nodesLength).toBeGreaterThan(1);
    });
  }
  
  colors.forEach((color) => {
    test(`Validate canvas node dragging for color: ${color}`, async () => {
      const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await codeGraph.selectGraph(GRAPH_ID);
      const initialAnalysis = await codeGraph.getCanvasAnalysis();
      await codeGraph.changeNodePosition(initialAnalysis[color][0].x, initialAnalysis[color][0].y);
      const finalAnalysis = await codeGraph.getCanvasAnalysis();
      expect(finalAnalysis[color][0].x).not.toBe(initialAnalysis.green[0].x);
      expect(finalAnalysis[color][0].y).not.toBe(initialAnalysis.green[0].y);
    });
  })

});
