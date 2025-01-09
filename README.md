[![Try Free](https://img.shields.io/badge/Try%20Free-FalkorDB%20Cloud-FF8101?labelColor=FDE900&link=https://app.falkordb.cloud)](https://app.falkordb.cloud)
[![Dockerhub](https://img.shields.io/docker/pulls/falkordb/falkordb?label=Docker)](https://hub.docker.com/r/falkordb/falkordb/)
[![Discord](https://img.shields.io/discord/1146782921294884966?style=flat-square)](https://discord.com/invite/6M4QwDXn2w)
[![Workflow](https://github.com/FalkorDB/code-graph/actions/workflows/nextjs.yml/badge.svg?branch=main)](https://github.com/FalkorDB/code-graph/actions/workflows/nextjs.yml)

![image](https://github.com/FalkorDB/code-graph/assets/753206/60f535ed-cf29-44b2-9005-721f11614803)

## Getting Started
[Live Demo](https://code-graph.falkordb.com/)

## Run locally
This project is composed of three pieces:

1. FalkorDB Graph DB - this is where your graphs are stored and queried
2. Code-Graph-Backend - backend logic
3. Code-Graph-Frontend - website

You'll need to start all three components:

### Run FalkorDB 

```bash
docker run -p 6379:6379 -it --rm falkordb/falkordb
```

### Run Code-Graph-Backend

#### Clone the Backend

```bash
git clone https://github.com/FalkorDB/code-graph-backend.git
```

#### Setup environment variables

`SECRET_TOKEN` - user defined token used to authorize the request

```bash
export FALKORDB_HOST=localhost FALKORDB_PORT=6379 \
    OPENAI_API_KEY=<YOUR OPENAI_API_KEY> SECRET_TOKEN=<YOUR_SECRECT_TOKEN> \
    FLASK_RUN_HOST=0.0.0.0 FLASK_RUN_PORT=5000
```

#### Install dependencies & run

```bash
cd code-graph-backend

pip install --no-cache-dir -r requirements.txt

flask --app api/index.py run --debug > flask.log 2>&1 &

```

### Run Code-Graph-Frontend

#### Clone the Frontend

```bash
git clone https://github.com/FalkorDB/code-graph.git
```

#### Setup environment variables

```bash
export BACKEND_URL=http://${FLASK_RUN_HOST}:${FLASK_RUN_PORT} \
    SECRET_TOKEN=<YOUR_SECRECT_TOKEN> OPENAI_API_KEY=<YOUR_OPENAI_API_KEY>
```

#### Install dependencies & run

```bash
cd code-graph
npm install
npm run dev
```

### Process a local repository
```bash
curl -X POST http://127.0.0.1:5000/analyze_folder -H "Content-Type: application/json" -d '{"path": "<PATH_TO_LOCAL_REPO>", "ignore": ["./.github", "./sbin", "./.git","./deps", "./bin", "./build"]}' -H "Authorization: <YOUR_SECRECT_TOKEN>"
```

Note: At the moment code-graph can analyze both the C & Python source files.
Support for additional languages e.g. JavaScript, Go, Java is planned to be added
in the future.

Browse to [http://localhost:3000](http://localhost:3000)
