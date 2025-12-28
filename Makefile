.PHONY: run docker-build docker-up docker-down migrate seed clean

run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

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