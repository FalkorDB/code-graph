<div align="center">
    
# Code Graph

[![Try Free](https://img.shields.io/badge/Try%20Free-FalkorDB%20Cloud-FF8101?labelColor=FDE900&link=https://app.falkordb.cloud)](https://app.falkordb.cloud)
[![Dockerhub](https://img.shields.io/docker/pulls/falkordb/falkordb?label=Docker)](https://hub.docker.com/r/falkordb/falkordb/)
[![Discord](https://img.shields.io/discord/1146782921294884966?style=flat-square)](https://discord.com/invite/6M4QwDXn2w)
[![Workflow](https://github.com/FalkorDB/code-graph/actions/workflows/nextjs.yml/badge.svg?branch=main)](https://github.com/FalkorDB/code-graph/actions/workflows/nextjs.yml)

**Visualize codebases as knowledge graphs to analyze dependencies, detect bottlenecks, and optimize projects.**

![FalkorDB Code Graph](https://github.com/user-attachments/assets/725e8ac0-8a64-474d-b2af-2de49b37293e)

</div>

## Quick Start

Try the [**Live Demo**](https://code-graph.falkordb.com/) to see Code Graph in action!

## Prerequisites

Before running locally, ensure you have:
- Docker installed
- Python 3.8+ with pip
- Node.js 16+ with npm
- OpenAI API key ([get one here](https://platform.openai.com/api-keys))

## Running Locally

Code Graph consists of three components that work together:

| Component | Purpose | Port |
|-----------|---------|------|
| **FalkorDB** | Graph database for storing and querying code relationships | 6379 |
| **Backend** | API server handling analysis logic | 5000 |
| **Frontend** | Web interface for visualization | 3000 |

### Step 1: Start FalkorDB

```bash
docker run -p 6379:6379 -it --rm falkordb/falkordb
```

### Step 2: Setup Backend

#### Clone and configure
```bash
git clone https://github.com/FalkorDB/code-graph-backend.git
cd code-graph-backend
```

#### Set environment variables
```bash
export FALKORDB_HOST=localhost
export FALKORDB_PORT=6379
export OPENAI_API_KEY=<YOUR_OPENAI_API_KEY>
export SECRET_TOKEN=<YOUR_SECRET_TOKEN>
export FLASK_RUN_HOST=0.0.0.0
export FLASK_RUN_PORT=5000
```

> **Tip**: Create a `.env` file with these variables for easier management

#### Install and run
```bash
pip install --no-cache-dir -r requirements.txt
flask --app api/index.py run --debug > flask.log 2>&1 &
```

### Step 3: Setup Frontend

#### Clone and configure
```bash
git clone https://github.com/FalkorDB/code-graph.git
cd code-graph
```

#### Set environment variables
```bash
export BACKEND_URL=http://localhost:5000
export SECRET_TOKEN=<YOUR_SECRET_TOKEN>
export OPENAI_API_KEY=<YOUR_OPENAI_API_KEY>
```

#### Install and run
```bash
npm install
npm run dev
```

### Step 4: Analyze Your Code

Once all services are running, analyze a local repository:

```bash
curl -X POST http://127.0.0.1:5000/analyze_folder \
  -H "Content-Type: application/json" \
  -H "Authorization: <YOUR_SECRET_TOKEN>" \
  -d '{
    "path": "/path/to/your/repo",
    "ignore": [
      "./.github",
      "./.git", 
      "./node_modules",
      "./build",
      "./dist"
    ]
  }'
```

Then visit [http://localhost:3000](http://localhost:3000) to view your code graph!

## Configuration

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `OPENAI_API_KEY` | Your OpenAI API key for code analysis | Yes | - |
| `SECRET_TOKEN` | Authorization token for API requests | Yes | - |
| `FALKORDB_HOST` | FalkorDB server hostname | No | localhost |
| `FALKORDB_PORT` | FalkorDB server port | No | 6379 |
| `FLASK_RUN_HOST` | Backend server host | No | 0.0.0.0 |
| `FLASK_RUN_PORT` | Backend server port | No | 5000 |

### Supported Languages

Currently supported:
- **C/C++**
- **Python**

Coming soon:
- **JavaScript/TypeScript**
- **Go**
- **Java**
- **Rust**
## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- **Email**: support@falkordb.com
- **Discord**: [Join our community](https://discord.gg/falkordb)
- **Issues**: [GitHub Issues](https://github.com/FalkorDB/code-graph/issues)
- **Docs**: [Documentation](https://docs.falkordb.com)

---

<div align="center">
Made with ❤️ by the FalkorDB team
</div>

### Consider ⭐️ to show your support!

code graph, code visualization, codebase analysis, dependency graph, software architecture, code dependencies, graph database, FalkorDB, code analysis tool, source code visualization, project dependencies, code structure analysis, software development tools, code mapping, dependency tracking, code relationships, software visualization, code exploration, development workflow, code insights, static code analysis, code comprehension, software engineering tools, code quality analysis, project structure visualization
