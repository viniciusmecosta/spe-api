import asyncio
import importlib
import json

from sqlalchemy import extract, select

from app.core.config import settings
from app.database.session import SessionLocal
from app.features.reports.report_service import report_service
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import User
from app.shared.enums import UserRole


async def compare() -> None:
    for module in (
        "app.features.companies.company_models",
        "app.features.printers.printer_models",
        "app.features.devices.device_models",
    ):
        importlib.import_module(module)
    differences = []
    compared = 0
    with SessionLocal() as session:
        actor = session.scalar(
            select(User).where(User.role == UserRole.MAINTAINER).limit(1)
        )
        if actor is None:
            raise RuntimeError("No maintainer in the development database")
        year_part = extract("year", TimeRecord.record_datetime)
        month_part = extract("month", TimeRecord.record_datetime)
        periods = session.execute(
            select(year_part, month_part).distinct().order_by(year_part, month_part)
        ).all()
        user_ids = session.scalars(select(User.id).order_by(User.id)).all()
        for year_value, month_value in periods:
            year, month = int(year_value), int(month_value)
            for user_id in user_ids:
                settings.DAILY_SUMMARY_READ_ENABLED = False
                legacy = await report_service.get_history_report(
                    session, user_id, month, year, actor
                )
                settings.DAILY_SUMMARY_READ_ENABLED = True
                summary = await report_service.get_history_report(
                    session, user_id, month, year, actor
                )
                compared += 1
                if legacy.model_dump(mode="json") != summary.model_dump(mode="json"):
                    differences.append({"user_id": user_id, "period": f"{year:04d}-{month:02d}"})
    print(json.dumps({"compared": compared, "differences": differences}, indent=2))
    if differences:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(compare())
