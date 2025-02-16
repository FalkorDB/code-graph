# CodeGraph - Knowledge Graph Visualization Tool

###Visualize your repository with our graph for code analysis

[![Try Free](https://img.shields.io/badge/Try%20Free-FalkorDB%20Cloud-FF8101?labelColor=FDE900&link=https://app.falkordb.cloud)](https://app.falkordb.cloud)
[![Dockerhub](https://img.shields.io/docker/pulls/falkordb/falkordb?label=Docker)](https://hub.docker.com/r/falkordb/falkordb/)
[![Discord](https://img.shields.io/discord/1146782921294884966?style=flat-square)](https://discord.com/invite/6M4QwDXn2w)
[![Workflow](https://github.com/FalkorDB/code-graph/actions/workflows/nextjs.yml/badge.svg?branch=main)](https://github.com/FalkorDB/code-graph/actions/workflows/nextjs.yml)
-

![Alt Text](https://res.cloudinary.com/dhd0k02an/image/upload/v1739719361/FalkorDB_-_Github_-_readme_jr6scy.gif)



**👉🏻[Live Demo](https://code-graph.falkordb.com/)**



## Running Locally  

This project consists of three core components:  

1. **FalkorDB Graph DB** – Stores and queries your graphs.  
2. **Code-Graph-Backend** – Handles backend logic.  
3. **Code-Graph-Frontend** – Provides the web interface.  

To set up the project, you’ll need to start all three components.  

### 1. Start FalkorDB  

Run the following command to start FalkorDB using Docker:  

```bash
docker run -p 6379:6379 -it --rm falkordb/falkordb
```

### 2. Start the Backend  

#### Clone the Backend Repository  

```bash
git clone https://github.com/FalkorDB/code-graph-backend.git
cd code-graph-backend
```

#### Set Up Environment Variables  

Define the required environment variables:  

```bash
export FALKORDB_HOST=localhost FALKORDB_PORT=6379 \
    OPENAI_API_KEY=<YOUR_OPENAI_API_KEY> SECRET_TOKEN=<YOUR_SECRET_TOKEN> \
    FLASK_RUN_HOST=0.0.0.0 FLASK_RUN_PORT=5000
```

`SECRET_TOKEN` is a user-defined token used for request authorization.  

#### Install Dependencies & Start the Backend  

```bash
pip install --no-cache-dir -r requirements.txt
flask --app api/index.py run --debug > flask.log 2>&1 &
```

### 3. Start the Frontend  

#### Clone the Frontend Repository  

```bash
git clone https://github.com/FalkorDB/code-graph.git
cd code-graph
```

#### Set Up Environment Variables  

```bash
export BACKEND_URL=http://${FLASK_RUN_HOST}:${FLASK_RUN_PORT} \
    SECRET_TOKEN=<YOUR_SECRET_TOKEN> OPENAI_API_KEY=<YOUR_OPENAI_API_KEY>
```

#### Install Dependencies & Start the Frontend  

```bash
npm install
npm run dev
```

### 4. Process a Local Repository  

Use the following `curl` command to analyze a local repository:  

```bash
curl -X POST http://127.0.0.1:5000/analyze_folder \
    -H "Content-Type: application/json" \
    -H "Authorization: <YOUR_SECRET_TOKEN>" \
    -d '{"path": "<PATH_TO_LOCAL_REPO>", "ignore": ["./.github", "./sbin", "./.git", "./deps", "./bin", "./build"]}'
```

**Note:** Currently, Code-Graph supports analyzing C and Python source files.  
Support for additional languages (e.g., JavaScript, Go, Java) is planned.  

### 5. Access the Web Interface  

Once everything is running, open your browser and go to:  

[http://localhost:3000](http://localhost:3000)  



## Community
Have questions or feedback? Reach out via:

* [GitHub Issues](https://github.com/FalkorDB/GraphRAG-SDK/issues)
* Join our [Discord](https://discord.com/invite/6M4QwDXn2w)

⭐️ If you find this repository helpful, please consider giving it a star!

Knowledge Graph, Code Analysis, Code Visualization, Dead Code Analysis, Graph Database
