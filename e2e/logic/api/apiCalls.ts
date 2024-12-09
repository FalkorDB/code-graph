import { getRequest, postRequest } from "../../infra/api/apiRequests";
import urls from '../../config/urls.json'
import { askQuestionResponse, createProjectResponse, fetchLatestRepoInfo, getNodeNeighborsResponse, getProjectResponse, searchAutoCompleteResponse, showPathResponse } from "./apiResponse";

export class ApiCalls {

    async createProject(projectUrl: string): Promise<createProjectResponse>{
        const result = await postRequest(urls.baseUrl + "api/repo?url=" + projectUrl);
        return await result.json();
    }

    async getProject(projectName: string): Promise<getProjectResponse>{
        const result = await getRequest(urls.baseUrl + "api/repo/" + projectName);
        return await result.json();
    }

    async projectInfo(projectName: string): Promise<fetchLatestRepoInfo>{
        const result = await getRequest(urls.baseUrl + "api/repo/" + projectName + "/info");
        return await result.json();
    }

    async showPath(projectName: string, sourceId: string, tragetId: string): Promise<showPathResponse>{
        const result = await postRequest(urls.baseUrl + "api/repo/" + projectName + "/" + sourceId + "?targetId=" + tragetId);
        return await result.json()
    }

    async askQuestion(projectName: string, question: string): Promise<askQuestionResponse>{
        const result = await postRequest(urls.baseUrl + "api/chat/" + projectName + "?msg=" + question);
        return await result.json()
    }

    async searchAutoComplete(projectName: string, searchInput: string): Promise<searchAutoCompleteResponse>{
        const result = await postRequest(urls.baseUrl + "api/repo/" + projectName + "?prefix=" + searchInput + "&type=autoComplete");
        return await result.json()
    }

    async getNodeNeighbors(projectName: string, nodeNumber: string): Promise<getNodeNeighborsResponse>{
        const result = await getRequest(urls.baseUrl + "api/repo/" + projectName + "/" + nodeNumber);
        return await result.json()
    }

}