.PHONY: dev test lint
dev:
	@echo "TODO: start server (uvicorn server.api:app) and web (vite) in HUDDLE_MODE=mock"
test:
	pytest -q
lint:
	ruff check server tests
