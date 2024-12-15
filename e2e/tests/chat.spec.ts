import { test, expect } from "@playwright/test";
import BrowserWrapper from "../infra/ui/browserWrapper";
import urls from "../config/urls.json";
import { ApiCalls } from "../logic/api/apiCalls";
import CodeGraph from "../logic/POM/codeGraph";
import { CHAT_OPTTIONS_COUNT, GRAPH_ID, Node_Add_Edge, Node_Import_Data, Node_Question, PROJECT_NAME } from "../config/constants";
import { delay } from "../logic/utils";

test.describe("Chat tests", () => {
  let browser: BrowserWrapper;

  test.beforeAll(async () => {
    browser = new BrowserWrapper();
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

    for (let i = 0; i < 5; i++) {
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
    for (let i = 0; i < 5; i++) {
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
    expect(await chat.isNodeVisibleInLastChatPath(Node_Import_Data)).toBe(true);
    expect(await chat.isNodeVisibleInLastChatPath(Node_Add_Edge)).toBe(true);
  });

  test("Verify unsuccessful node path connection between two nodes in chat", async () => {
    const chat = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await chat.selectGraph(GRAPH_ID);
    await chat.clickOnshowPathBtn();
    await chat.insertInputForShowPath("1", Node_Add_Edge);
    await chat.insertInputForShowPath("2", Node_Import_Data);
    await delay(500);
    expect(await chat.isNotificationError()).toBe(true);
  });

  test("Validate error notification and its closure when sending an empty question in chat", async () => {
    const chat = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await chat.selectGraph(GRAPH_ID);
    await chat.clickAskquestionBtn();
    expect(await chat.isNotificationError()).toBe(true);
    await chat.clickOnNotificationErrorCloseBtn();
    expect(await chat.isNotificationError()).toBe(false);
  });

  for (let index = 0; index < 5; index++) {
    const questionNumber = index + 1;
    test(`Validate displaying question ${index} in chat after selection from options menu`, async () => {
      const chat = await browser.createNewPage(CodeGraph, urls.baseUrl);
      await chat.selectGraph(GRAPH_ID);
      await chat.clickOnQuestionOptionsMenu();
      const selectedQuestion = await chat.selectAndGetQuestionInOptionsMenu(questionNumber.toString());  
      expect(selectedQuestion).toEqual(await chat.getLastQuestionInChat())
    });
  }

  test(`Validate consistent UI responses for repeated questions in chat`, async () => {
    const chat = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await chat.selectGraph(GRAPH_ID);
    const responses: string[] = [];
    for (let i = 0; i < 3; i++) {
      await chat.sendMessage(Node_Question);
      const result = await chat.getTextInLastChatElement();
      const number = result.match(/\d+/g)?.[0]!;
      responses.push(number);
    }
    const identicalResponses = responses.every((value) => value === responses[0]);
    expect(identicalResponses).toBe(true);
  });

  test(`Validate UI response matches API response for a given question in chat`, async () => {
    const chat = await browser.createNewPage(CodeGraph, urls.baseUrl);
    await chat.selectGraph(GRAPH_ID);
  
    await chat.sendMessage(Node_Question);
    const uiResponse = await chat.getTextInLastChatElement();
    const number = uiResponse.match(/\d+/g)?.[0]!;
    
    const api = new ApiCalls();
    const apiResponse = await api.askQuestion(PROJECT_NAME, Node_Question);
    expect(number).toEqual(apiResponse.result.response.match(/\d+/g)?.[0]);
  });
});
