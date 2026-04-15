import logging
import os
import pytz
import time
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import api_router
from app.core.config import settings
from app.core.logger import setup_logging
from app.services.backup_service import backup_service
from app.services.sync_service import sync_service
from app.services.telegram_service import telegram_service

setup_logging()
logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    tz = pytz.timezone(settings.TIMEZONE)

    trigger_aligned = CronTrigger(minute='0,10,20,30,40,50', timezone=tz)

    scheduler.add_job(backup_service.run_daily_backup_routine, trigger=trigger_aligned, id="daily_backup_email",
                      max_instances=1, coalesce=True)
    scheduler.add_job(telegram_service.execute_hourly_backup, trigger=trigger_aligned, id="hourly_backup_telegram",
                      max_instances=1, coalesce=True)
    scheduler.add_job(telegram_service.send_managerial_report, trigger=trigger_aligned, id="daily_report_telegram",
                      max_instances=1, coalesce=True)

    scheduler.add_job(backup_service.clean_old_logs, trigger=trigger_aligned, id="cleanup_routine_logs",
                      max_instances=1, coalesce=True)

    if settings.OPERATION_MODE == "EXPORTADOR":
        scheduler.add_job(sync_service.send_database_to_consumer, trigger=trigger_aligned, id="hourly_sync_db",
                          max_instances=1, coalesce=True)
        scheduler.add_job(sync_service.check_and_sync_all, trigger=trigger_aligned, id="sync_time_records",
                          max_instances=1, coalesce=True)

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


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    host = request.client.host if request.client else "127.0.0.1"
    logger.info(f"{host} - \"{request.method} {request.url.path}\" {response.status_code} {process_time:.4f}s")
    return response


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code >= 500:
        logger.error(f"HTTP {exc.status_code} na rota {request.url.path}: {exc.detail}", exc_info=True)
    else:
        logger.warning(f"HTTP {exc.status_code} na rota {request.url.path}: {exc.detail}")

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
    logger.warning(f"Erro de validação em {request.method} {request.url.path}: {exc.errors()}")
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        content={"detail": "Validation Error", "errors": exc.errors()})


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    logger.error(f"Database error em {request.url.path}: {str(exc)}", exc_info=True)
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        content={"detail": "A database error occurred."})


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unexpected error em {request.url.path}: {str(exc)}", exc_info=True)
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
