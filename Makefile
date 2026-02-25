.PHONY: up down logs backend-test backend-lint migrate smoke-auth pre-push-check prod-smoke

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

prod-up:
	docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build

prod-down:
	docker compose -f docker-compose.prod.yml --env-file .env.production down

prod-logs:
	docker compose -f docker-compose.prod.yml --env-file .env.production logs -f --tail=200

smoke-auth:
	./scripts/smoke_auth.sh

pre-push-check:
	./scripts/pre_push_check.sh

prod-smoke:
	@HOST="$${PROD_HOST:-104.236.237.83}"; \
	echo "Running production smoke checks against $$HOST"; \
	echo "--- GET /"; \
	curl -fsS -I --max-time 10 "http://$$HOST:3000" | sed -n '1,6p'; \
	echo "--- GET /api/v1/health/live"; \
	curl -fsS --max-time 10 "http://$$HOST:3000/api/v1/health/live"; echo; \
	echo "--- GET /api/v1/health/ready"; \
	curl -fsS --max-time 10 "http://$$HOST:3000/api/v1/health/ready"; echo; \
	echo "--- GET /api/v1/public/teaser/kpis?sport_key=basketball_nba"; \
	curl -fsS --max-time 10 "http://$$HOST:3000/api/v1/public/teaser/kpis?sport_key=basketball_nba"; echo; \
	echo "prod-smoke complete"
