from fastapi import APIRouter

from app.api.routes import (
    auth,
    users,
    time_records,
    work_schedules,
    holidays,
    adjustments,
    reports,
    payroll,
    work_hours,
    anomalies,
    device
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(time_records.router, prefix="/time-records", tags=["time-records"])
api_router.include_router(work_schedules.router, prefix="/work-schedules", tags=["work-schedules"])
api_router.include_router(holidays.router, prefix="/holidays", tags=["holidays"])
api_router.include_router(adjustments.router, prefix="/adjustments", tags=["adjustments"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(payroll.router, prefix="/payroll", tags=["payroll"])
api_router.include_router(work_hours.router, prefix="/work-hours", tags=["work-hours"])
api_router.include_router(anomalies.router, prefix="/anomalies", tags=["anomalies"])
api_router.include_router(device.router, prefix="/device", tags=["device"])