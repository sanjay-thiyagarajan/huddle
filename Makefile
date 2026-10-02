.PHONY: install dev test lint
PY := .venv/bin

install:
	uv venv -q --python 3.12 .venv
	uv pip install -q -e ".[dev]"

dev:
	HUDDLE_MODE=mock $(PY)/uvicorn server.api:app --reload --port 8000

test:
	HUDDLE_MODE=mock $(PY)/pytest -q

lint:
	$(PY)/ruff check server tests
