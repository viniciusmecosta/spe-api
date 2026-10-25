.PHONY: setup run run-prod docker-build docker-up docker-logs docker-down migrate upgrade seed clean test lint dump restore db-restore-test venv db-init db-pg-up db-dump-ddl db-dump-data db-dump-sqlite db-apply-dump db-check db-migrate-all

ifeq ($(OS),Windows_NT)
    PYTHON := .venv\Scripts\python.exe
    ALEMBIC := .venv\Scripts\alembic.exe
else
    PYTHON := .venv/bin/python
    ALEMBIC := .venv/bin/alembic
endif

# Instala e sincroniza as dependências.
setup:
	uv sync --locked --no-build

# Inicia a API em desenvolvimento.
run:
	granian --interface asgi --host 0.0.0.0 --port 8000 --reload --reload-paths app app.main:app

# Inicia a API em produção.
run-prod:
	granian --interface asgi --host 0.0.0.0 --port 8000 app.main:app

# Cria uma nova revisão Alembic.
migrate:
	$(ALEMBIC) revision --autogenerate -m "$(msg)"

# Aplica as migrações Alembic pendentes.
upgrade:
	$(ALEMBIC) upgrade head

# Insere os dados iniciais da aplicação.
seed:
	$(PYTHON) app/initial_data.py

# Constrói as imagens Docker.
docker-build:
	docker compose build

# Inicia todos os serviços Docker.
docker-up:
	docker compose up -d

# Acompanha os logs dos containers.
docker-logs:
	docker compose logs -f

# Encerra os serviços Docker.
docker-down:
	docker compose down

# Remove caches e bytecode do Python.
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# Executa os testes automatizados.
test:
	.venv/bin/pytest

lint:
	uv run --no-sync ruff check app scripts

# Gera o backup completo do PostgreSQL.
dump:
	$(PYTHON) scripts/db_manager.py --dump

# Gera somente a estrutura do PostgreSQL.
db-dump-ddl:
	$(PYTHON) scripts/db_manager.py --dump-ddl

# Gera somente os inserts do PostgreSQL.
db-dump-data:
	$(PYTHON) scripts/db_manager.py --dump-data

# Restaura spe.zip.enc da raiz ou de scripts/.
restore:
	$(PYTHON) scripts/apply_sql_to_postgresql.py --restore --yes

# Testa o backup em um banco temporário sem alterar o banco principal.
db-restore-test:
	$(PYTHON) scripts/verify_backup_restore.py

# Abre um terminal com o ambiente virtual.
venv:
	@if [ "$(OS)" = "Windows_NT" ]; then \
		cmd /k ".venv\\Scripts\\activate.bat" ; \
	else \
		bash -c "source .venv/bin/activate && exec bash" ; \
	fi

# Inicia somente o PostgreSQL.
db-pg-up:
	docker compose up -d --wait db

# Aplica a estrutura no PostgreSQL já provisionado.
db-init:
	$(ALEMBIC) upgrade head

# Converte spe.db em inserts para PostgreSQL.
db-dump-sqlite:
	$(PYTHON) scripts/export_sqlite_to_postgresql.py

# Limpa os dados e aplica o dump convertido.
db-apply-dump:
	$(PYTHON) scripts/apply_sql_to_postgresql.py --yes

# Compara todos os dados do SQLite e PostgreSQL.
db-check:
	$(PYTHON) scripts/verify_parity.py

# Migra SQLite na revisão 002, aplica as demais migrações e cria a apuração histórica.
db-migrate-all:
	$(ALEMBIC) upgrade 002
	$(PYTHON) scripts/export_sqlite_to_postgresql.py
	$(PYTHON) scripts/apply_sql_to_postgresql.py --dry-run
	$(PYTHON) scripts/apply_sql_to_postgresql.py --yes
	$(ALEMBIC) upgrade head
	$(PYTHON) scripts/verify_parity.py
	$(PYTHON) -m scripts.backfill_daily_summaries --execute
	$(PYTHON) scripts/verify_parity.py
