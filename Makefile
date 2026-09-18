.PHONY: setup run run-prod docker-build docker-up docker-logs docker-down migrate upgrade seed clean test lint dump restore venv db-pg-up db-dump-sqlite db-apply-dump db-check db-migrate-all

ifeq ($(OS),Windows_NT)
    PYTHON := .venv\Scripts\python.exe
    ALEMBIC := .venv\Scripts\alembic.exe
else
    PYTHON := .venv/bin/python
    ALEMBIC := .venv/bin/alembic
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
	$(ALEMBIC) revision --autogenerate -m "$(msg)"

# Aplica migracoes pendentes no banco via Alembic. Use para criar ou atualizar o schema no PostgreSQL.
upgrade:
	$(ALEMBIC) upgrade head

# Popula banco com dados iniciais basicos. Use ao inicializar instalacao nova.
seed:
	$(PYTHON) app/initial_data.py

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

# Gera backup desmembrado do PostgreSQL: DDL live (spe-db.sql) e inserts live (spe_dump.sql) em spe.zip.
dump: db-pg-up
	$(PYTHON) scripts/db_manager.py --dump

# Extrai a DDL da estrutura atual diretamente do PostgreSQL ativo para spe-db.sql.
db-dump-ddl: db-pg-up
	$(PYTHON) scripts/db_manager.py --dump-ddl

# Extrai apenas os inserts de dados diretamente do PostgreSQL ativo para spe_dump.sql.
db-dump-data: db-pg-up
	$(PYTHON) scripts/db_manager.py --dump-data

# Restaura o banco a partir do backup recebido por e-mail (spe.zip ou SQL). Limpa dados existentes e aplica novos.
restore: db-pg-up
	$(PYTHON) scripts/apply_sql_to_postgresql.py --restore

# Abre shell com ambiente virtual ativado. Use para entrar no ambiente virtual no terminal.
venv:
	@if [ "$(OS)" = "Windows_NT" ]; then \
		cmd /k ".venv\\Scripts\\activate.bat" ; \
	else \
		bash -c "source .venv/bin/activate && exec bash" ; \
	fi

# Sobe apenas o container PostgreSQL no Docker e aguarda estar pronto. Use para ligar o banco de dados.
db-pg-up:
	docker compose up -d --wait db

# Exporta dados do SQLite (spe.db) em script SQL de inserts compativel com PostgreSQL. Use para gerar dump dos dados.
db-dump-sqlite:
	$(PYTHON) scripts/export_sqlite_to_postgresql.py

# Limpa o PostgreSQL e aplica o dump de dados SQL com transacao atomica e constraints diferidas.
db-apply-dump:
	$(PYTHON) scripts/apply_sql_to_postgresql.py

# Audita todas as linhas e celulas comparando SQLite e PostgreSQL. Use para verificar integridade e paridade dos dados.
db-check:
	$(PYTHON) scripts/verify_parity.py

# Fluxo completo: sobe banco, aplica Alembic 001, gera dump do SQLite, aplica no PostgreSQL e audita paridade.
db-migrate-all: db-pg-up upgrade db-dump-sqlite db-apply-dump db-check