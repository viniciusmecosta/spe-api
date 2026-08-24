from fastapi import APIRouter

from app.core.config import settings
from app.features.adjustments.adjustment_router import router as adjustments_router
from app.features.auth.auth_router import router as auth_router
from app.features.companies.company_router import router as companies_router
from app.features.devices.device_router import (
    biometrics_router,
    device_credentials_router,
    firmware_router,
    router as device_router,
    sync_router,
)
from app.features.holidays.holiday_router import router as holidays_router
from app.features.payroll.payroll_router import router as payroll_router
from app.features.printers.printer_router import router as printers_router
from app.features.reports.report_router import dashboard_router, router as reports_router
from app.features.system.system_router import (
    audit_router,
    backup_router,
    routine_logs_router,
    telegram_actions_router,
)
from app.features.time_records.time_record_router import router as time_records_router
from app.features.timesheets.timesheet_router import anomalies_router, router as timesheets_router
from app.features.users.user_router import router as users_router
from app.features.users.work_schedule_router import router as schedules_router

api_router = APIRouter()


@api_router.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    return {"status": "ok", "app": "SPE", "version": settings.APP_VERSION}


api_router.include_router(adjustments_router, prefix="/adjustments", tags=["Adjustments"])
api_router.include_router(anomalies_router, prefix="/anomalies", tags=["Anomalies"])
api_router.include_router(audit_router, prefix="/audit", tags=["Audit"])
api_router.include_router(auth_router, prefix="/auth", tags=["Auth"])
api_router.include_router(backup_router, prefix="/backup", tags=["Backup"])
api_router.include_router(biometrics_router, prefix="/biometric", tags=["Biometric"])
api_router.include_router(companies_router, prefix="/companies", tags=["Companies"])
api_router.include_router(dashboard_router, prefix="/dashboard", tags=["Dashboard"])
api_router.include_router(device_router, prefix="/device", tags=["Device"])
api_router.include_router(device_credentials_router, prefix="/device-credentials", tags=["Device Credentials"])
api_router.include_router(firmware_router, prefix="/firmware", tags=["Firmware OTA"])
api_router.include_router(holidays_router, prefix="/holidays", tags=["Holidays"])
api_router.include_router(payroll_router, prefix="/payroll", tags=["Payroll"])
api_router.include_router(printers_router, prefix="/printers", tags=["Printers"])
api_router.include_router(reports_router, prefix="/reports", tags=["Reports"])
api_router.include_router(routine_logs_router, prefix="/routine-logs", tags=["Routine Logs"])
api_router.include_router(schedules_router, prefix="/schedules", tags=["Schedules"])
api_router.include_router(sync_router, prefix="/sync", tags=["Sync"])
api_router.include_router(telegram_actions_router, prefix="/telegram", tags=["Telegram"])
api_router.include_router(time_records_router, prefix="/time-records", tags=["Time Records"])
api_router.include_router(timesheets_router, prefix="/timesheets", tags=["Timesheets"])
api_router.include_router(users_router, prefix="/users", tags=["Users"])

