.PHONY: setup run run-prod docker-build docker-up docker-down migrate seed clean test lint reset-db dump restore venv db-export db-pg-up db-pg-populate db-pg-setup db-pg-reset db-check

PYTHON ?= uv run python

setup:
	pip install uv
	uv sync

run:
	$(PYTHON) -m granian --interface asgi --host 0.0.0.0 --port 8000 --reload --reload-paths app app.main:app

run-prod:
	$(PYTHON) -m granian --interface asgi --host 0.0.0.0 --port 8000 app.main:app

migrate:
	uv run alembic revision --autogenerate -m "$(msg)"

upgrade:
	uv run alembic upgrade head

seed:
	$(PYTHON) app/initial_data.py

docker-build:
	docker-compose build

docker-up:
	docker-compose up -d

docker-logs:
	docker-compose logs -f

docker-down:
	docker-compose down

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

test:
	poetry run pytest

lint:
	mypy app

reset-db:
	@echo "Resetando e repopulando banco PostgreSQL..."
	$(PYTHON) scripts/db_manager.py --populate
	@echo "Banco PostgreSQL resetado e populado com sucesso!"

dump:
	@echo "Gerando dump oficial fidedigno do PostgreSQL (spe_dump.sql)..."
	$(PYTHON) scripts/db_manager.py --dump
	@echo "Dump PostgreSQL gerado com sucesso!"

restore:
	@echo "Restaurando banco PostgreSQL a partir de spe_dump.sql..."
	$(PYTHON) scripts/db_manager.py --restore
	@echo "Restauração do PostgreSQL concluída com sucesso!"

venv:
	@echo "Iniciando um novo shell com o ambiente virtual ativado..."
	@if [ "$(OS)" = "Windows_NT" ]; then \
		cmd /k ".venv\\Scripts\\activate.bat" ; \
	else \
		bash -c "source .venv/bin/activate && exec bash" ; \
	fi

db-export:
	@echo "Exportando DDL e dados do SQLite para PostgreSQL..."
	$(PYTHON) scripts/db_manager.py --export-all

db-pg-up:
	@echo "Subindo container PostgreSQL no Docker..."
	docker compose up -d --wait db

db-pg-populate:
	@echo "Populando PostgreSQL a partir de scripts/data_inserts_postgresql.sql..."
	$(PYTHON) scripts/db_manager.py --populate

db-pg-setup:
	@echo "Subindo banco PostgreSQL e aplicando dados..."
	docker compose up -d --wait db
	$(PYTHON) scripts/db_manager.py --populate
	$(PYTHON) scripts/db_manager.py --verify

db-pg-reset:
	@echo "Resetando PostgreSQL (recriando container e volume limpo)..."
	docker compose down db -v
	docker compose up -d --wait db
	$(PYTHON) scripts/db_manager.py --populate
	@echo "PostgreSQL resetado e populado com sucesso!"

db-check:
	@echo "Verificando paridade entre SQLite e PostgreSQL..."
	$(PYTHON) scripts/db_manager.py --verify