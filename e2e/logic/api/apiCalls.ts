import { getRequest, postRequest } from "../../infra/api/apiRequests";
import urls from '../../config/urls.json'
import { askQuestionResponse, createProjectResponse, fetchLatestRepoInfo, getProjectResponse, showPathResponse } from "./apiResponse";

export class ApiCalls {

    async createProject(projectname: string): Promise<createProjectResponse>{
        const result = await postRequest(urls.baseUrl + "api/repo?url=" + projectname);
        return await result.json();
    }

    async getProject(projectName: string): Promise<getProjectResponse>{
        const result = await getRequest(urls.baseUrl + "api/repo/" + projectName);
        return await result.json();
    }

    async fetchLatestRepoInfo(projectName: string): Promise<fetchLatestRepoInfo>{
        const result = await postRequest(urls.baseUrl + "api/repo/" + projectName);
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

}