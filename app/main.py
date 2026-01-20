import logging
import os
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes import api_router
from app.core.config import settings
from app.core.mqtt import mqtt
# Importa listeners para registrar os decorators @mqtt.subscribe
from app.services.backup_service import backup_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    trigger = CronTrigger(
        hour='10,14',
        minute=00,
        timezone=settings.TIMEZONE
    )
    scheduler.add_job(backup_service.send_database_backup, trigger=trigger, id="daily_backup")
    scheduler.start()
    logger.info(f"Agendador iniciado (Backups agendados para 10h e 14h)")

    await mqtt.mqtt_startup()
    logger.info("Módulo MQTT iniciado")

    yield

    await mqtt.mqtt_shutdown()
    logger.info("Módulo MQTT encerrado")

    scheduler.shutdown()
    logger.info("Agendador encerrado.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"Validation error: {exc.errors()}")
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        content={"detail": "Validation Error", "errors": exc.errors()})


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    logger.error(f"Database error: {str(exc)}")
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        content={"detail": "A database error occurred."})


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {str(exc)}")
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        content={"detail": f"An unexpected error occurred: {str(exc)}"})


app.include_router(api_router, prefix=settings.API_V1_STR)
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=settings.UPLOAD_DIR), name="static")


@app.get("/")
def root():
    return {"message": "Welcome to SPE API"}
