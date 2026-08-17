.PHONY: setup run run-prod docker-build docker-up docker-down migrate seed clean test lint reset-db dump restore venv

setup:
	pip install uv
	uv sync

run:
	granian --interface asgi --host 0.0.0.0 --port 8000 --reload --reload-paths app app.main:app

run-prod:
	granian --interface asgi --host 0.0.0.0 --port 8000 app.main:app

migrate:
	alembic revision --autogenerate -m "$(msg)"

upgrade:
	alembic upgrade head

seed:
	python app/initial_data.py

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
	@echo "Apagando banco de dados..."
	rm -f spe.db spe.db-shm spe.db-wal
	@echo "Recriando estrutura e populando dados..."
	make upgrade
	make seed
	@echo "Banco resetado com sucesso!"

dump:
	@echo "Gerando dump do banco de dados (spe_dump.sql)..."
	sqlite3 spe.db .dump > spe_dump.sql
	@echo "Dump gerado com sucesso!"

restore:
	@echo "Limpando banco de dados atual..."
	rm -f spe.db spe.db-shm spe.db-wal
	@echo "Restaurando banco a partir de spe_dump.sql..."
	sqlite3 spe.db < spe_dump.sql
	@echo "Restauração concluída com sucesso!"

venv:
	@echo "Iniciando um novo shell com o ambiente virtual ativado..."
	@if [ "$(OS)" = "Windows_NT" ]; then \
		cmd /k ".venv\\Scripts\\activate.bat" ; \
	else \
		bash -c "source .venv/bin/activate && exec bash" ; \
	fi