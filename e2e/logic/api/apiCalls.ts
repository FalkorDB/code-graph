import { getRequest, postRequest, postJsonRequest } from "../../infra/api/apiRequests";
import urls from '../../config/urls.json'
import { askQuestionResponse, createProjectResponse, fetchLatestRepoInfo, getNodeNeighborsResponse, getProjectResponse, searchAutoCompleteResponse, showPathResponse } from "./apiResponse";

export class ApiCalls {

    async createProject(projectUrl: string): Promise<createProjectResponse>{
        const result = await postJsonRequest(urls.baseUrl + "analyze_repo", { repo_url: projectUrl });
        return await result.json();
    }

    async getProject(projectName: string): Promise<getProjectResponse>{
        const result = await getRequest(urls.baseUrl + "graph_entities?repo=" + projectName);
        return await result.json();
    }

    async projectInfo(projectName: string): Promise<fetchLatestRepoInfo>{
        const result = await postJsonRequest(urls.baseUrl + "repo_info", { repo: projectName });
        return await result.json();
    }

    async showPath(projectName: string, sourceId: string, tragetId: string): Promise<showPathResponse>{
        const result = await postJsonRequest(urls.baseUrl + "find_paths", { repo: projectName, src: Number(sourceId), dest: Number(tragetId) });
        return await result.json()
    }

    async askQuestion(projectName: string, question: string): Promise<askQuestionResponse>{
        const result = await postJsonRequest(urls.baseUrl + "chat", { repo: projectName, msg: question });
        return await result.json()
    }

    async searchAutoComplete(projectName: string, searchInput: string): Promise<searchAutoCompleteResponse>{
        const result = await postJsonRequest(urls.baseUrl + "auto_complete", { repo: projectName, prefix: searchInput });
        return await result.json()
    }

    async getNodeNeighbors(projectName: string, nodeNumber: string): Promise<getNodeNeighborsResponse>{
        const result = await postJsonRequest(urls.baseUrl + "get_neighbors", { repo: projectName, node_ids: [Number(nodeNumber)] });
        return await result.json()
    }

}