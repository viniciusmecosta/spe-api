import logging
import os
import socket
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import api_router
from app.core.config import settings
from app.services.backup_service import backup_service
from app.services.sync_service import sync_service
from app.services.telegram_service import telegram_service


class UvicornHostFilter(logging.Filter):
    def __init__(self):
        super().__init__()
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("10.255.255.255", 1))
            self.ip = s.getsockname()[0]
            s.close()
        except Exception:
            self.ip = "127.0.0.1"

    def filter(self, record):
        if record.msg == "Uvicorn running on %s://%s:%d (Press CTRL+C to quit)":
            if len(record.args) == 3 and record.args[1] == "0.0.0.0":
                record.args = (record.args[0], self.ip, record.args[2])
        return True


logging.getLogger("uvicorn.error").addFilter(UvicornHostFilter())

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    tz = pytz.timezone(settings.TIMEZONE)
    start_time = datetime.now(tz) + timedelta(minutes=1)

    trigger_legacy = IntervalTrigger(minutes=60, start_date=start_time, timezone=tz)
    scheduler.add_job(backup_service.run_daily_backup_routine, trigger=trigger_legacy, id="legacy_daily_backup")

    trigger_telegram_hourly = IntervalTrigger(minutes=60, start_date=start_time, timezone=tz)
    scheduler.add_job(telegram_service.execute_hourly_backup, trigger=trigger_telegram_hourly,
                      id="telegram_hourly_backup")

    trigger_telegram_report = IntervalTrigger(minutes=30, start_date=start_time, timezone=tz)
    scheduler.add_job(telegram_service.send_managerial_report, trigger=trigger_telegram_report,
                      id="telegram_daily_report")

    if settings.OPERATION_MODE == "EXPORTADOR":
        trigger_sync = IntervalTrigger(hours=1, start_date=start_time, timezone=tz)
        scheduler.add_job(sync_service.send_database_to_consumer, trigger=trigger_sync, id="hourly_sync_db")

    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.APP_VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
    swagger_ui_parameters={
        "docExpansion": "list",
        "tryItOutEnabled": True,
        "defaultModelsExpandDepth": -1,
        "defaultModelExpandDepth": 0,
        "persistAuthorization": True,
        "displayRequestDuration": True,
    },
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == status.HTTP_404_NOT_FOUND:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "erro": "Rota não encontrada.",
                "mensagem": "A URL acessada não existe. Verifique a documentação em /docs para ver as rotas disponíveis."
            }
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        content={"detail": "Validation Error", "errors": exc.errors()})


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        content={"detail": "A database error occurred."})


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        content={"detail": "An unexpected error occurred."})


@app.get("/", include_in_schema=False)
def root():
    return {
        "sistema": settings.PROJECT_NAME,
        "versao": settings.APP_VERSION,
        "status": "Online",
        "documentacao": "/docs"
    }


app.include_router(api_router, prefix=settings.API_V1_STR)
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=settings.UPLOAD_DIR), name="static")
