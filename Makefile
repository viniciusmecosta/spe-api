.PHONY: setup run run-prod docker-build docker-up docker-down migrate seed clean

setup:
	pip install uv
	uv venv
	uv pip install -r requirements.txt

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