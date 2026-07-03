import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import api_router
from app.core.config import settings
from app.core.exceptions import setup_exception_handlers
from app.core.lifespan import lifespan
from app.core.logger import setup_logging
from app.middleware.request_logging import RequestLoggingMiddleware

setup_logging()
logger = logging.getLogger(__name__)

os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

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

app.add_middleware(RequestLoggingMiddleware)

setup_exception_handlers(app)


@app.get("/", include_in_schema=False)
def root():
    return {
        "sistema": settings.PROJECT_NAME,
        "versao": settings.APP_VERSION,
        "status": "Online",
        "documentacao": "/docs"
    }


app.include_router(api_router, prefix=settings.API_V1_STR)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")
