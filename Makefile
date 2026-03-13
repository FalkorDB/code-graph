.PHONY: help install test e2e lint lint-py lint-fe clean build-dev build-prod run-dev run-prod docker-falkordb docker-stop

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install all dependencies (backend + frontend)
	uv sync --all-extras
	npm install --prefix ./app

build-dev: ## Build frontend for development
	npm --prefix ./app run build:dev

build-prod: ## Build frontend for production
	npm --prefix ./app run build

test: ## Run backend tests
	uv run python -m pytest tests/ --verbose

e2e: ## Run end-to-end Playwright tests
	npx playwright test

lint: lint-py lint-fe ## Run all linters

lint-py: ## Run Python linting (ruff)
	uv run ruff check .

lint-fe: ## Run frontend linting (TypeScript)
	npm --prefix ./app run lint

clean: ## Clean up build and test artifacts
	rm -rf app/dist/
	rm -rf test-results/
	rm -rf playwright-report/
	rm -rf .pytest_cache/
	rm -rf __pycache__/
	find . -name "*.pyc" -delete
	find . -name "*.pyo" -delete

run-dev: build-dev ## Run development server (Python backend serving built frontend)
	uv run flask --app api/index.py run --host $${HOST:-127.0.0.1} --port $${PORT:-5000} --debug

run-prod: build-prod ## Run production server
	uv run flask --app api/index.py run --host $${HOST:-0.0.0.0} --port $${PORT:-5000}

docker-falkordb: ## Start FalkorDB in Docker for testing
	docker run -d --name falkordb-test -p 6379:6379 falkordb/falkordb:latest

docker-stop: ## Stop test containers
	docker stop falkordb-test || true
	docker rm falkordb-test || true
