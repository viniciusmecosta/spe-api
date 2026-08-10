from app.api.v1 import (
    adjustments,
    anomalies,
    audit,
    auth,
    backup,
    biometrics,
    companies,
    dashboard,
    device,
    device_credentials,
    firmware,
    holidays,
    payroll,
    printers,
    reports,
    routine_logs,
    sync,
    telegram_actions,
    time_records,
    timesheets,
    users,
)
from app.core.config import settings
from fastapi import APIRouter

api_router = APIRouter()


@api_router.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    return {"status": "ok", "app": "SPE", "version": settings.APP_VERSION}


api_router.include_router(adjustments.router, prefix="/adjustments", tags=["Adjustments"])
api_router.include_router(anomalies.router, prefix="/anomalies", tags=["Anomalies"])
api_router.include_router(audit.router, prefix="/audit", tags=["Audit"])
api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(backup.router, prefix="/backup", tags=["Backup"])
api_router.include_router(biometrics.router, prefix="/biometric", tags=["Biometric"])
api_router.include_router(companies.router, prefix="/companies", tags=["Companies"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
api_router.include_router(device.router, prefix="/device", tags=["Device"])
api_router.include_router(device_credentials.router, prefix="/device-credentials", tags=["Device Credentials"])
api_router.include_router(firmware.router, prefix="/firmware", tags=["Firmware OTA"])
api_router.include_router(holidays.router, prefix="/holidays", tags=["Holidays"])
api_router.include_router(payroll.router, prefix="/payroll", tags=["Payroll"])
api_router.include_router(printers.router, prefix="/printers", tags=["Printers"])
api_router.include_router(reports.router, prefix="/reports", tags=["Reports"])
api_router.include_router(routine_logs.router, prefix="/routine-logs", tags=["Routine Logs"])
api_router.include_router(sync.router, prefix="/sync", tags=["Sync"])
api_router.include_router(telegram_actions.router, prefix="/telegram", tags=["Telegram"])
api_router.include_router(time_records.router, prefix="/time-records", tags=["Time Records"])
api_router.include_router(timesheets.router, prefix="/timesheets", tags=["Timesheets"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
