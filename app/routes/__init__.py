from fastapi import APIRouter
from app.api.routes import auth

api_router = APIRouter()

@api_router.get("/health")
def health_check():
    return {"status": "ok", "app": "SPE"}

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])