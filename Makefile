.PHONY: setup run run-prod docker-build docker-up docker-down migrate seed clean test lint reset-db dump restore venv db-export db-pg-up db-pg-populate db-pg-setup db-pg-reset db-check db-migrate-all db_pg_up db_migrate_all db-restore db_restore

ifeq ($(OS),Windows_NT)
    PYTHON := .venv\Scripts\python.exe
else
    PYTHON := .venv/bin/python
endif


# Instala gerenciador uv e sincroniza dependencias. Use ao configurar o ambiente pela primeira vez.
setup:
	pip install uv
	uv sync

# Inicia a API com auto-reload. Use durante o desenvolvimento local.
run:
	granian --interface asgi --host 0.0.0.0 --port 8000 --reload --reload-paths app app.main:app

# Inicia a API em modo producao. Use para execucao em ambiente final/producao.
run-prod:
	granian --interface asgi --host 0.0.0.0 --port 8000 app.main:app

# Gera revisao de migracao Alembic. Use apos alterar modelos (ex: make migrate msg="descricao").
migrate:
	alembic revision --autogenerate -m "$(msg)"

# Aplica migracoes pendentes no banco. Use para atualizar o schema via Alembic.
upgrade:
	alembic upgrade head

# Popula banco com dados iniciais basicos. Use ao inicializar instalacao nova.
seed:
	python app/initial_data.py

# Constroi imagens Docker do projeto. Use apos alterar Dockerfile ou dependencias.
docker-build:
	docker-compose build

# Sobe os servicos Docker em background. Use para rodar ambiente conteinerizado.
docker-up:
	docker-compose up -d

# Exibe logs em tempo real dos containers. Use para monitorar ou depurar os servicos Docker.
docker-logs:
	docker-compose logs -f

# Para e remove os containers Docker. Use para encerrar os servicos conteinerizados.
docker-down:
	docker-compose down

# Remove arquivos compilados e caches Python. Use para limpeza do diretorio local.
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# Executa suite de testes automatizados com pytest. Use para validar testes e regras de negocio.
test:
	.venv/bin/pytest

# Executa verificador estatico de tipos mypy. Use para checar tipagem e consistencia do codigo.
lint:
	mypy app

# Gera dump SQL oficial fidedigno do PostgreSQL. Use para criar backup manual completo.
dump:
	$(PYTHON) scripts/db_manager.py --dump

# Restaura o banco a partir do spe.zip do email ou de arquivos SQL. Use para aplicar backup no PostgreSQL.
restore: db-pg-up
	$(PYTHON) scripts/db_manager.py --restore

db-restore: restore

db_restore: restore

# Abre shell com ambiente virtual ativado. Use para entrar no ambiente virtual no terminal.
venv:
	@if [ "$(OS)" = "Windows_NT" ]; then \
		cmd /k ".venv\\Scripts\\activate.bat" ; \
	else \
		bash -c "source .venv/bin/activate && exec bash" ; \
	fi

# Exporta DDL e inserts do SQLite para scripts/. Use para inspecionar ou exportar manualmente.
db-export:
	$(PYTHON) scripts/db_manager.py --export-all

# Sobe apenas o container PostgreSQL no Docker e aguarda estar pronto. Use para ligar o banco.
db-pg-up:
	docker compose up -d --wait db

# Popula o PostgreSQL com os scripts SQL existentes. Use para recarregar dados sem reexportar.
db-pg-populate:
	$(PYTHON) scripts/db_manager.py --populate

# Sobe o banco, popula e audita paridade. Use para setup e validacao completa do PostgreSQL.
db-pg-setup: db-pg-up
	$(PYTHON) scripts/db_manager.py --populate
	$(PYTHON) scripts/db_manager.py --verify

# Reinicia container e volume Docker do PostgreSQL do zero. Use para reset total limpo do banco.
db-pg-reset:
	docker compose down db -v
	docker compose up -d --wait db
	$(PYTHON) scripts/db_manager.py --populate

# Audita todas as linhas e celulas comparando SQLite e PostgreSQL. Use para verificar integridade dos dados.
db-check:
	$(PYTHON) scripts/db_manager.py --verify

# Fluxo completo: sobe banco, exporta SQLite, popula PostgreSQL e audita celula a celula. Use para migrar com 1 comando.
db-migrate-all: db-pg-up
	$(PYTHON) scripts/db_manager.py --export-all
	$(PYTHON) scripts/db_manager.py --populate
	$(PYTHON) scripts/db_manager.py --verify

db_pg_up: db-pg-up

db_migrate_all: db-migrate-all