<div align="center">

# CodeGraph - Knowledge Graph Visualization Tool

**Visualize codebases as knowledge graphs to analyze dependencies, detect bottlenecks, and optimize projects.**

[![Try Free](https://img.shields.io/badge/Try%20Free-FalkorDB%20Cloud-FF8101?labelColor=FDE900&link=https://app.falkordb.cloud)](https://app.falkordb.cloud)
[![Dockerhub](https://img.shields.io/docker/pulls/falkordb/falkordb?label=Docker)](https://hub.docker.com/r/falkordb/falkordb/)
[![Discord](https://img.shields.io/discord/1146782921294884966?style=flat-square)](https://discord.com/invite/6M4QwDXn2w)

![Alt Text](https://res.cloudinary.com/dhd0k02an/image/upload/v1739719361/FalkorDB_-_Github_-_readme_jr6scy.gif)

**[Live Demo](https://code-graph.falkordb.com/)**

</div>

## Project Structure

```
code-graph/
├── api/                  # Python backend (Flask)
│   ├── index.py          # Main Flask app with API routes
│   ├── graph.py          # Graph operations (FalkorDB)
│   ├── llm.py            # LLM integration for chat
│   ├── project.py        # Project management
│   ├── info.py           # Repository info
│   ├── prompts.py        # LLM prompts
│   ├── auto_complete.py  # Auto-completion
│   ├── analyzers/        # Source code analyzers (Python, Java, C, C#)
│   ├── entities/         # Entity models
│   ├── git_utils/        # Git operations
│   └── code_coverage/    # Code coverage utilities
├── app/                  # React frontend (Vite)
│   ├── src/              # Frontend source code
│   │   ├── App.tsx       # Main application component
│   │   ├── main.tsx      # Entry point
│   │   ├── components/   # React components
│   │   └── lib/          # Utility functions
│   ├── public/           # Static assets
│   ├── package.json      # Frontend dependencies
│   ├── vite.config.ts    # Vite configuration
│   └── tsconfig.json     # TypeScript configuration
├── tests/                # Backend tests
├── e2e/                  # End-to-end tests (Playwright)
├── Dockerfile            # Unified Docker build
├── docker-compose.yml    # Docker Compose setup
├── Makefile              # Development commands
├── start.sh              # Container startup script
├── pyproject.toml        # Python project configuration
└── .env.template         # Environment variables template
```

## Running Locally

### Prerequisites

- Python 3.12+
- Node.js 20+
- FalkorDB instance (local or cloud)

### 1. Start FalkorDB

**Option A:** Free cloud instance at [app.falkordb.cloud](https://app.falkordb.cloud/signup)

**Option B:** Run locally with Docker:

```bash
docker run -p 6379:6379 -it --rm falkordb/falkordb
```

### 2. Set Up Environment Variables

Copy the template and configure:

```bash
cp .env.template .env
```

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `OPENAI_API_KEY` | Your OpenAI API key for code analysis | Yes | - |
| `SECRET_TOKEN` | User-defined token for request authorization | Yes | - |
| `FALKORDB_HOST` | FalkorDB server hostname | No | localhost |
| `FALKORDB_PORT` | FalkorDB server port | No | 6379 |

Edit `.env` with your values:

```bash
FALKORDB_HOST=localhost
FALKORDB_PORT=6379
OPENAI_API_KEY=<YOUR_OPENAI_API_KEY>
SECRET_TOKEN=<YOUR_SECRET_TOKEN>
```

### 3. Install Dependencies

```bash
# Install backend dependencies
pip install -e ".[test]"

# Install frontend dependencies
npm install --prefix ./app
```

Or using Make:

```bash
make install
```

### 4. Build & Start

```bash
# Build the frontend
npm --prefix ./app run build

# Start the backend (serves both API and frontend)
flask --app api/index.py run --debug
```

The application will be available at [http://localhost:5000](http://localhost:5000).

### Development Mode

For frontend development with hot-reload:

```bash
# Terminal 1: Start the Python backend
flask --app api/index.py run --debug --port 5000

# Terminal 2: Start the Vite dev server (proxies API calls to backend)
cd app && npm run dev
```

The Vite dev server runs on `http://localhost:3000` and proxies API requests to the Flask backend on port 5000.

### Using Make

```bash
make install       # Install all dependencies
make build-dev     # Build frontend (development)
make build-prod    # Build frontend (production)
make run-dev       # Build + start dev server
make run-prod      # Build + start production server
make test          # Run backend tests
make lint          # Run frontend linting
make clean         # Clean build artifacts
```

## Running with Docker

### Using Docker Compose

```bash
docker-compose up
```

This starts both FalkorDB and the CodeGraph application.

### Using Docker Directly

```bash
docker build -t code-graph .

docker run -p 5000:5000 \
  -e FALKORDB_HOST=host.docker.internal \
  -e FALKORDB_PORT=6379 \
  -e OPENAI_API_KEY=<YOUR_KEY> \
  -e SECRET_TOKEN=<YOUR_TOKEN> \
  code-graph
```

## Creating a Code Graph

### Analyze a Local Folder

```bash
curl -X POST http://127.0.0.1:5000/analyze_folder \
  -H "Content-Type: application/json" \
  -H "Authorization: <YOUR_SECRET_TOKEN>" \
  -d '{"path": "<FULL_PATH_TO_FOLDER>", "ignore": [".github", ".git"]}'
```

### Analyze a GitHub Repository

```bash
curl -X POST http://127.0.0.1:5000/analyze_repo \
  -H "Content-Type: application/json" \
  -H "Authorization: <YOUR_SECRET_TOKEN>" \
  -d '{"repo_url": "https://github.com/user/repo"}'
```

## Supported Languages

- Python
- Java
- C
- C#

Support for additional languages is planned.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/list_repos` | List all available repositories |
| GET | `/graph_entities?repo=<name>` | Get graph entities for a repository |
| POST | `/get_neighbors` | Get neighbors of specified nodes |
| POST | `/auto_complete` | Auto-complete entity names |
| POST | `/repo_info` | Get repository information |
| POST | `/find_paths` | Find paths between two nodes |
| POST | `/chat` | Chat with the code graph using natural language |
| POST | `/analyze_folder` | Analyze a local source folder |
| POST | `/analyze_repo` | Analyze a GitHub repository |
| POST | `/list_commits` | List commits of a repository |
| POST | `/switch_commit` | Switch to a specific commit |

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- [GitHub Issues](https://github.com/FalkorDB/code-graph/issues)
- [Discord](https://discord.com/invite/6M4QwDXn2w)
- [Documentation](https://docs.falkordb.com)
- Email: support@falkordb.com

---

<div align="center">
If you find this repository helpful, please consider giving it a star!
</div>
