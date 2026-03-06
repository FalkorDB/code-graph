.PHONY: help install test lint clean build-dev build-prod run-dev run-prod

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install all dependencies (backend + frontend)
	pip install -e ".[test]"
	npm install --prefix ./app

build-dev: ## Build frontend for development
	npm --prefix ./app run build:dev

build-prod: ## Build frontend for production
	npm --prefix ./app run build

test: ## Run backend tests
	python -m pytest tests/ --verbose

lint: ## Run linting (frontend)
	npm --prefix ./app run lint

clean: ## Clean up build and test artifacts
	rm -rf app/dist/
	rm -rf test-results/
	rm -rf playwright-report/
	rm -rf __pycache__/
	find . -name "*.pyc" -delete
	find . -name "*.pyo" -delete

run-dev: build-dev ## Run development server (Python backend serving built frontend)
	flask --app api/index.py run --host $${HOST:-127.0.0.1} --port $${PORT:-5000} --debug

run-prod: build-prod ## Run production server
	flask --app api/index.py run --host $${HOST:-0.0.0.0} --port $${PORT:-5000}

docker-falkordb: ## Start FalkorDB in Docker for testing
	docker run -d --name falkordb-test -p 6379:6379 falkordb/falkordb:latest

docker-stop: ## Stop test containers
	docker stop falkordb-test || true
	docker rm falkordb-test || true
