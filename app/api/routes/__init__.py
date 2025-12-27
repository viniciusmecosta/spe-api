from fastapi import APIRouter
from app.api.routes import auth, time_records, adjustments

api_router = APIRouter()

@api_router.get("/health")
def health_check():
    return {"status": "ok", "app": "SPE"}

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(time_records.router, prefix="/time-records", tags=["time-records"])
api_router.include_router(adjustments.router, prefix="/adjustments", tags=["adjustments"])