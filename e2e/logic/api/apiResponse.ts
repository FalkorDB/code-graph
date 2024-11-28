export interface createProjectResponse {
    message: string;
}

export interface getProjectResponse {
    result: {
        entities: {
            edges: {
                alias: string;
                dest_node: number;
                id: number;
                properties: Record<string, unknown>;
                relation: string;
                src_node: number;
            }[];
            nodes: {
                alias: string;
                id: number;
                labels: string[];
                properties: {
                    ext?: string;
                    name: string;
                    path: string;
                    doc?: string;
                    src_end?: number;
                    src_start?: number;
                };
            }[];
        };
        status: string;
    };
}

export interface fetchLatestRepoInfo {
    result: {
        info: {
            commit: string;
            edge_count: number;
            node_count: number;
            repo_url: string;
        };
        status: string;
    };
}


export interface showPathResponse {
    result: {
        paths: Array<Array<{
            alias: string;
            id: number;
            labels?: string[];
            properties: {
                args?: [string, string][];
                name: string;
                path: string;
                src?: string;
                src_end?: number;
                src_start?: number;
            };
            dest_node?: number;
            relation?: string;
            src_node?: number;
        }>>;
        status: string;
    };
}

export interface askQuestionResponse{
    result: {
        response: string;
        status: string;
    }
}

export interface searchAutoCompleteResponse {
    result: {
      completions: {
        alias: string;
        id: number;
        labels: string[];
        properties: {
          args: any[];
          name: string;
          path: string;
          src_end: number;
          src_start: number;
        };
      }[];
      status: string;
    };
  }

  export interface getNodeNeighborsResponse {
    result: {
      neighbors: {
        edges: {
          alias: string;
          dest_node: number;
          id: number;
          properties: Record<string, any>;
          relation: string;
          src_node: number;
        }[];
        nodes: {
          alias: string;
          id: number;
          labels: string[];
          properties: {
            args: [string, string][];
            doc?: string;
            name: string;
            path: string;
            ret_type?: string;
            src: string;
            src_end: number;
            src_start: number;
          };
        }[];
      };
      status: string;
    };
  }
  
  

