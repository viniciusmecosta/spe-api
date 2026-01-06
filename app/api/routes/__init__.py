from fastapi import APIRouter

from app.api.routes import auth, time_records, adjustments, work_hours, users, reports, holidays, payroll

api_router = APIRouter()


@api_router.get("/")
def root():
    return {"status": "ok", "message": "API V1 is running"}


@api_router.get("/health")
def health_check():
    return {"status": "ok", "app": "SPE"}


api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(time_records.router, prefix="/time-records", tags=["time-records"])
api_router.include_router(adjustments.router, prefix="/adjustments", tags=["adjustments"])
api_router.include_router(work_hours.router, prefix="/work-hours", tags=["work-hours"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(holidays.router, prefix="/holidays", tags=["holidays"])
api_router.include_router(payroll.router, prefix="/payroll", tags=["payroll"])
