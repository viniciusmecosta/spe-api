from fastapi import APIRouter

from app.api.routes import (
    auth,
    users,
    time_records,
    work_schedules,
    work_hours,
    holidays,
    adjustments,
    anomalies,
    reports,
    payroll,
    device,
    audit
)

api_router = APIRouter()


@api_router.get("/health")
def health_check():
    return {"status": "ok", "app": "SPE"}


api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(time_records.router, prefix="/time-records", tags=["Time Records"])
api_router.include_router(work_schedules.router, prefix="/work-schedules", tags=["Work Schedules"])
api_router.include_router(work_hours.router, prefix="/work-hours", tags=["Work Hours"])
api_router.include_router(holidays.router, prefix="/holidays", tags=["Holidays"])
api_router.include_router(adjustments.router, prefix="/adjustments", tags=["Adjustments"])
api_router.include_router(anomalies.router, prefix="/anomalies", tags=["Anomalies"])
api_router.include_router(reports.router, prefix="/reports", tags=["Reports"])
api_router.include_router(payroll.router, prefix="/payroll", tags=["Payroll"])
api_router.include_router(device.router, prefix="/device", tags=["Device"])
api_router.include_router(audit.router, prefix="/audit", tags=["Audit"])
