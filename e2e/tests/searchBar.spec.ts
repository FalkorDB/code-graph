import { test, expect } from "@playwright/test";
import BrowserWrapper from "../infra/ui/browserWrapper";
import CodeGraph from "../logic/POM/codeGraph";
import urls from "../config/urls.json";
import { GRAPHRAG_SDK } from "../config/constants";
import { delay, findFirstNodeWithSrc, findNodeByName } from "../logic/utils";
import { nodes, searchData, specialCharacters } from "../config/testData";
import { ApiCalls } from "../logic/api/apiCalls";

test.describe("search bar tests", () => {
  let browser: BrowserWrapper;

  test.beforeAll(async () => {
    browser = new BrowserWrapper();
  });

  test.afterAll(async () => {
    await browser.closeBrowser();
  });

  // searchData.slice(0, 2).forEach(({ searchInput }) => {
  //   test(`Verify search bar auto-complete behavior for input: ${searchInput} via UI`, async () => {
  //     const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
  //     await codeGraph.selectGraph(GRAPHRAG_SDK);
  //     await codeGraph.fillSearchBar(searchInput);
  //     await delay(1000);
  //     const textList = await codeGraph.getSearchBarElementsText();
  //     textList.forEach((text) => {
  //       expect(text.toLowerCase()).toContain(searchInput);
  //     });
  //   });
  // });

  // searchData.slice(2, 4).forEach(({ searchInput, completedSearchInput }) => {
  //   test(`Validate search bar updates with selected element: ${searchInput}`, async () => {
  //     const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
  //     await codeGraph.selectGraph(GRAPHRAG_SDK);
  //     await codeGraph.fillSearchBar(searchInput);
  //     await codeGraph.selectSearchBarOptionBtn("1");
  //     expect(await codeGraph.getSearchBarInputValue()).toBe(
  //       completedSearchInput
  //     );
  //   });
  // });

  // searchData.slice(0, 2).forEach(({ searchInput }) => {
  //   test(`Verify auto-scroll scroll in search bar list for: ${searchInput}`, async () => {
  //     const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
  //     await codeGraph.selectGraph(GRAPHRAG_SDK);
  //     await codeGraph.fillSearchBar(searchInput);
  //     await codeGraph.scrollToBottomInSearchBarList();
  //     expect(await codeGraph.isScrolledToBottomInSearchBarList()).toBe(true);
  //   });
  // });

  // specialCharacters.forEach(({ character, expectedRes }) => {
  //   test(`Verify entering special characters behavior in search bar for: ${character}`, async () => {
  //     const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
  //     await codeGraph.selectGraph(GRAPHRAG_SDK);
  //     await codeGraph.fillSearchBar(character);
  //     await delay(1000);
  //     expect((await codeGraph.getSearchBarInputValue()).includes(character)).toBe(expectedRes);
  //   });
  // });

  // searchData.slice(0, 2).forEach(({ searchInput}) => {
  //   test(`search bar auto complete via ui and validating via api for: ${searchInput}`, async () => {
  //     const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
  //     await codeGraph.selectGraph(GRAPHRAG_SDK);
  //     await codeGraph.fillSearchBar(searchInput);
  //     const count = await codeGraph.getSearchAutoCompleteCount();
  //     const api = new ApiCalls();
  //     const response = await api.searchAutoComplete(GRAPHRAG_SDK, searchInput);
  //     expect(count).toBe(response.result.completions.length);
  //   });
  // })

  nodes.forEach(({nodeName})=> {
    test(`Verify canvas focuses on node ${nodeName} after search`, async () => {//here
      const codeGraph = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await browser.setPageToFullScreen();
      await codeGraph.selectGraph(GRAPHRAG_SDK);
      await codeGraph.getGraphDetails();
      await codeGraph.fillSearchBar(nodeName);
      await codeGraph.selectSearchBarOptionBtn("1");
      await codeGraph.waitForCanvasAnimationToEnd();
      await codeGraph.rightClickAtCanvasCenter();
      expect(await codeGraph.getNodeDetailsHeader()).toContain(nodeName.toUpperCase());
    });
  })
})