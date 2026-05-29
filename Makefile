.PHONY: install test run-api lint

install:
	pip install -e ".[dev]"

test:
	pytest tests/ -v

run-api:
	uvicorn apps.api.main:create_app --factory --reload --host 0.0.0.0 --port 8000

lint:
	ruff check apps tests
