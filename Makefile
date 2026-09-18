.PHONY: setup run run-prod docker-build docker-up docker-logs docker-down migrate upgrade seed clean test lint dump restore venv db-init db-pg-up db-dump-ddl db-dump-data db-dump-sqlite db-apply-dump db-check db-migrate-all

ifeq ($(OS),Windows_NT)
    PYTHON := .venv\Scripts\python.exe
    ALEMBIC := .venv\Scripts\alembic.exe
else
    PYTHON := .venv/bin/python
    ALEMBIC := .venv/bin/alembic
endif

# Instala e sincroniza as dependências.
setup:
	pip install uv
	uv sync

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

# Verifica a tipagem do projeto.
lint:
	mypy app

# Gera o backup completo do PostgreSQL.
dump: db-pg-up
	$(PYTHON) scripts/db_manager.py --dump

# Gera somente a estrutura do PostgreSQL.
db-dump-ddl: db-pg-up
	$(PYTHON) scripts/db_manager.py --dump-ddl

# Gera somente os inserts do PostgreSQL.
db-dump-data: db-pg-up
	$(PYTHON) scripts/db_manager.py --dump-data

# Restaura spe.zip ou spe_dump.sql da raiz ou de scripts/.
restore: db-pg-up
	$(PYTHON) scripts/apply_sql_to_postgresql.py --restore --yes

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

# Inicia o PostgreSQL e aplica a estrutura do banco.
db-init:
	docker compose up -d --wait db
	$(ALEMBIC) upgrade head

# Converte spe.db em inserts para PostgreSQL.
db-dump-sqlite:
	$(PYTHON) scripts/export_sqlite_to_postgresql.py

# Limpa os dados e aplica o dump convertido.
db-apply-dump: db-pg-up
	$(PYTHON) scripts/apply_sql_to_postgresql.py --yes

# Compara todos os dados do SQLite e PostgreSQL.
db-check: db-pg-up
	$(PYTHON) scripts/verify_parity.py

# Executa a migração completa e confere os dados.
db-migrate-all: db-pg-up
	$(ALEMBIC) upgrade head
	$(PYTHON) scripts/export_sqlite_to_postgresql.py
	$(PYTHON) scripts/apply_sql_to_postgresql.py --yes
	$(PYTHON) scripts/verify_parity.py
