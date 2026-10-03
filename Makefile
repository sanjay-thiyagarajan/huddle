.PHONY: install dev test lint build e2e docker mcp-inspect
PY := .venv/bin

install:
	uv venv -q --python 3.12 .venv
	uv pip install -q -e ".[dev]"
	cd web && npm install

# Mock mode: no AWS credentials needed. API on :8000, simulator on http://localhost:5173
dev:
	@test -d .venv || $(MAKE) install
	@test -d web/node_modules || (cd web && npm install)
	@trap 'kill 0' INT TERM EXIT; \
	HUDDLE_MODE=mock HUDDLE_PORT=8000 $(PY)/uvicorn server.api:app --reload --port 8000 & \
	cd web && npm run dev -- --host & \
	wait

build:
	cd web && npm run build

test:
	HUDDLE_MODE=mock $(PY)/pytest -q

# Browser tests (Playwright + installed Chrome): demo flows, failure path, axe accessibility audit
e2e:
	cd web && npx playwright test

# Interop check from a non-Python MCP client (the official Inspector CLI, Node). Needs `make dev` running.
mcp-inspect:
	npx -y @modelcontextprotocol/inspector@2.9.0 --cli http://localhost:8000/mcp --transport http --method tools/list

docker:
	docker compose up --build   # http://localhost:8000, mock mode

lint:
	$(PY)/ruff check server tests
