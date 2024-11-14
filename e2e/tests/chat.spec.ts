import { test, expect } from "@playwright/test";
import BrowserWrapper from "../infra/ui/browserWrapper";
import urls from "../config/urls.json";
import { ApiCalls } from "../logic/api/apiCalls";
import CodeGraph from "../logic/POM/codeGraph";
import { CHAT_OPTTIONS_COUNT, GRAPH_ID, Node_Add_Edge, Node_Import_Data, Node_Question } from "../config/constants";
import { delay } from "../logic/utils";

test.describe("Chat tests", () => {
  let browser: BrowserWrapper;
  let api: ApiCalls;

  test.beforeAll(async () => {
    browser = new BrowserWrapper();
    api = new ApiCalls();
    await api.createProject(urls.graphRAGuRL);
  });

  test.afterAll(async () => {
    await browser.closeBrowser();
  });

  test(`Validate clicking the lightbulb button displays the correct options at the end of the chat`, async () => {
    const chat = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await chat.selectGraph(GRAPH_ID);
    await chat.clickOnLightBulbBtn();
    const count = await chat.getLastChatElementButtonCount();
    expect(count).toBe(CHAT_OPTTIONS_COUNT);
  });

  test(`Validate that multiple consecutive questions receive individual answers`, async () => {
    const chat = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await chat.selectGraph(GRAPH_ID);
    const isLoadingArray: boolean[] = [];

    for (let i = 0; i < 10; i++) {
      await chat.sendMessage(Node_Question);
      const isLoading: boolean = await chat.getpreviousQuestionLoadingImage();
      isLoadingArray.push(isLoading);
      if (i > 0) {
        const prevIsLoading = isLoadingArray[i - 1];
        expect(prevIsLoading).toBe(false);
      }
    }
  });

  test("Verify auto-scroll and manual scroll in chat", async () => {
    const chat = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await chat.selectGraph(GRAPH_ID);
    for (let i = 0; i < 10; i++) {
      await chat.sendMessage(Node_Question);
    }
    await delay(500);
    await chat.scrollToTop();
    const { scrollTop } = await chat.getScrollMetrics();
    expect(scrollTop).toBeLessThanOrEqual(1);
    await chat.sendMessage("Latest Message");
    await delay(500);
    expect(await chat.isAtBottom()).toBe(true);
  });

  test("Verify successful node path connection between two nodes in chat", async () => {
    const chat = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await chat.selectGraph(GRAPH_ID);
    await chat.clickOnshowPathBtn();
    await chat.insertInputForShowPath("1", Node_Import_Data);
    await chat.insertInputForShowPath("2", Node_Add_Edge);
    await delay(200);
    expect(await chat.isNodeVisibleInLastChatPath(Node_Import_Data)).toBe(true);
    expect(await chat.isNodeVisibleInLastChatPath(Node_Add_Edge)).toBe(true);
  });

  test("Verify unsuccessful node path connection between two nodes in chat", async () => {
    const chat = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await chat.selectGraph(GRAPH_ID);
    await chat.clickOnshowPathBtn();
    await chat.insertInputForShowPath("1", Node_Add_Edge);
    await chat.insertInputForShowPath("2", Node_Import_Data);
    await delay(200);
    expect(await chat.isNotificationNoPathFound()).toBe(true);
  });
});
