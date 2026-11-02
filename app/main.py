import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.body_limit import RequestBodyLimitMiddleware

from app.core.config import settings
from app.core.exceptions import setup_exception_handlers
from app.core.lifespan import lifespan
from app.core.logger import setup_logging
from app.middleware.request_logging import RequestLoggingMiddleware
from app.router import api_router as api_v1_router

setup_logging()
logger = logging.getLogger(__name__)

Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
public_upload_dir = os.path.join(settings.UPLOAD_DIR, "public")
Path(public_upload_dir).mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.APP_VERSION,
    openapi_url="/api/v1/openapi.json",
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

app.add_middleware(RequestBodyLimitMiddleware, max_body_size=settings.UPLOAD_REQUEST_MAX_BYTES)
app.add_middleware(RequestLoggingMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Export-Status", "X-Export-Generated-Count", "X-Export-Failed-Count"],
)

setup_exception_handlers(app)


@app.get("/", include_in_schema=False)
def root():
    return {
        "sistema": settings.PROJECT_NAME,
        "versao": settings.APP_VERSION,
        "status": "Online",
        "documentacao": "/docs"
    }


app.include_router(api_v1_router, prefix="/api/v1")
from app.features.companies.logo_compatibility import public_upload

app.add_api_route('/uploads/{filename}', public_upload, include_in_schema=False)
