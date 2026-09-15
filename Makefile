.PHONY: up down test lint fmt migrate

up:      ; docker compose up --build
down:    ; docker compose down
migrate: ; cd backend && alembic upgrade head
test:    ; cd backend && pytest -q
lint:    ; cd backend && ruff check . && mypy app worker
fmt:     ; cd backend && ruff format . && ruff check --fix .
