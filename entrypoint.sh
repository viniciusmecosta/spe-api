#!/bin/bash
set -e

# Rodar migrações do banco de dados
echo "Running database migrations..."
alembic upgrade head

# Criar dados iniciais (Admin user)
echo "Creating initial data..."
python app/initial_data.py

# Iniciar a aplicação
echo "Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000