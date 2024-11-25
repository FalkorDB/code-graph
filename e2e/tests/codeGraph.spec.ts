import { test, expect } from "@playwright/test";
import BrowserWrapper from "../infra/ui/browserWrapper";
import CodeGraph from "../logic/POM/codeGraph";
import urls from "../config/urls.json";
import { GRAPH_ID } from "../config/constants";
import { delay } from "../logic/utils";
import { searchData, specialCharacters } from "../config/testData";

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
      expect(await codeGraph.isNotificationError()).toBe(expectedRes);
    });
  });
});
