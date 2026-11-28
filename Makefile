.PHONY: db up down logs migrate test reset-db

db:
	docker compose up -d db

up:
	docker compose --profile apps up --build -d

down:
	docker compose down

logs:
	docker compose --profile apps logs -f

migrate:
	docker compose exec backend alembic upgrade head

test:
	docker compose exec backend python -m pytest tests

reset-db:
	docker compose down -v
	docker compose up -d db
