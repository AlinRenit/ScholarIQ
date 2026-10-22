.PHONY: setup api web test test-backend test-frontend lint compliance migrate up down

VENV := .venv
PY := $(VENV)/bin/python

setup:
	python3 -m venv $(VENV)
	$(PY) -m pip install -e "backend[dev]"
	cd frontend && npm ci

migrate:
	cd backend && ../$(VENV)/bin/alembic upgrade head

api:
	cd backend && ../$(VENV)/bin/uvicorn scholariq.main:create_app --factory --reload --port 8000

web:
	cd frontend && npm run dev

test: test-backend test-frontend

test-backend:
	cd backend && ../$(VENV)/bin/pytest

test-frontend:
	cd frontend && npm test

lint:
	cd backend && ../$(VENV)/bin/ruff check . && ../$(VENV)/bin/ruff format --check . && ../$(VENV)/bin/mypy scholariq
	cd frontend && npm run typecheck && npm run lint

compliance:
	cd backend && ../$(VENV)/bin/python -m scholariq.compliance.scanner ..

up:
	docker compose up --build

down:
	docker compose down
