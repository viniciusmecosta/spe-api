.PHONY: run docker-build docker-up docker-down migrate seed clean

# Rodar localmente (Requer Python 3.11+ e venv ativo)
run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Gerar nova migração (Ex: make migrate msg="add user table")
migrate:
	alembic revision --autogenerate -m "$(msg)"

# Aplicar migrações
upgrade:
	alembic upgrade head

# Rodar seed de dados
seed:
	python app/initial_data.py

# Docker
docker-build:
	docker-compose build

docker-up:
	docker-compose up -d

docker-logs:
	docker-compose logs -f

docker-down:
	docker-compose down

# Limpeza
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete