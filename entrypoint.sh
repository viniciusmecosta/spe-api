#!/bin/bash
set -e

alembic upgrade head

python app/initial_data.py

exec uvicorn app.main:app --host 0.0.0.0 --port 8000