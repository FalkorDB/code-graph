import { test, expect } from "@playwright/test";
import BrowserWrapper from "../infra/ui/browserWrapper";
import urls from "../config/urls.json";
import { ApiCalls } from "../logic/api/apiCalls";
import { Node_Question, PROJECT_NAME } from "../config/constants";

test.describe("Api tests", () => {
  let api: ApiCalls;

  test.beforeAll(async () => {
    api = new ApiCalls();
    await api.createProject(urls.graphRAGuRL);
  });

  test("Validates API response structure after project creation and retrieval", async () => {
    const result = await api.getProject(PROJECT_NAME);
    expect(result).toEqual(
      expect.objectContaining({
        result: expect.objectContaining({
          entities: expect.objectContaining({
            edges: expect.any(Array),
            nodes: expect.any(Array),
          }),
          status: "success",
        }),
      })
    );
  });

  test("Validate structure of API response for latest repository info", async () => {
    const response = await api.fetchLatestRepoInfo(PROJECT_NAME);
    expect(response).toEqual(
      expect.objectContaining({
        result: expect.objectContaining({
          info: expect.objectContaining({
            commit: expect.any(String),
            edge_count: expect.any(Number),
            node_count: expect.any(Number),
            repo_url: expect.any(String),
          }),
          status: "success",
        }),
      })
    );
  });

  test("Validate API response for paths between nodes", async () => {
    const response = await api.showPath(PROJECT_NAME, "4", "485");
    expect(response).toEqual(
      expect.objectContaining({
        result: expect.objectContaining({
          paths: expect.any(Array),
          status: "success",
        }),
      })
    );
  });

  test("Validate API response for asking a graph-related question", async () => {
    const response = await api.askQuestion(PROJECT_NAME, Node_Question);
    expect(response).toEqual(
      expect.objectContaining({
        result: expect.objectContaining({
          response: expect.any(String),
          status: "success",
        }),
      })
    );
  });
});
