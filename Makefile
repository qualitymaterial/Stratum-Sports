.PHONY: up down logs backend-test backend-lint migrate

up:
	docker compose up --build

down:
	docker compose down -v

logs:
	docker compose logs -f --tail=200

migrate:
	docker compose run --rm backend alembic upgrade head

backend-test:
	docker compose run --rm backend pytest -q

backend-lint:
	docker compose run --rm backend ruff check app tests
