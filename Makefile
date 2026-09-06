.PHONY: check ui test dev-reload dev-smoke
check:
	uv run --extra dev ruff check src tests scripts
	uv run --extra dev ruff format --check src tests scripts
	uv run --extra dev pytest --cov=specsearch --cov-fail-under=90
ui:
	npm ci
	npm run build
test: check ui
	npm run test:e2e
dev-reload:
	docker compose up -d --build --force-recreate --wait --wait-timeout 60
dev-smoke:
	python3 scripts/docker_smoke.py
