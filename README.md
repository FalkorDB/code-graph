[![Dockerhub](https://img.shields.io/docker/pulls/falkordb/falkordb?label=Docker)](https://hub.docker.com/r/falkordb/falkordb/)
[![Discord](https://img.shields.io/discord/1146782921294884966?style=flat-square)](https://discord.gg/ErBEqN9E)
[![Workflow](https://github.com/FalkorDB/code-graph/actions/workflows/nextjs.yml/badge.svg?branch=main)](https://github.com/FalkorDB/code-graph/actions/workflows/nextjs.yml)

![image](https://github.com/FalkorDB/code-graph/assets/753206/60f535ed-cf29-44b2-9005-721f11614803)

## Getting Started

Run FalkorDB

```bash
docker run -p 6379:6379 -it --rm falkordb/falkordb
```

Install node packages

```bash
npm install
```

Set your OpenAI key

```
export OPENAI_API_KEY=YOUR_OPENAI_API_KEY
```

Run the development server:

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.
