import logging
from datetime import date
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.reports.template_service import template_service
from app.features.time_records.time_record_models import TimeRecord
from app.features.timesheets.anomaly_service import anomaly_service
from app.features.users.user_models import User
from app.shared import deps
from app.shared.enums import DayOfWeek, RecordType
from app.shared.timezone import local_day_bounds, to_app_timezone
from app.utils.formatters import build_report_names

logger = logging.getLogger(__name__)


class DailyReportService:
    def __init__(self, db: Annotated[AsyncSession, Depends(deps.get_async_db)] = None):
        self.db = db

    async def generate_daily_report_html(self, db: AsyncSession | None = None, target_date: date | None = None) -> str:
        session = db if db is not None else self.db
        assert session is not None
        assert target_date is not None
        try:
            formatted_date = target_date.strftime("%d/%m/%Y")
            day_name = DayOfWeek(target_date.weekday()).nome

            start_local, end_local = local_day_bounds(target_date)

            stmt = (
                select(TimeRecord, User)
                .join(User, TimeRecord.user_id == User.id)
                .where(TimeRecord.record_datetime >= start_local)
                .where(TimeRecord.record_datetime < end_local)
                .where(TimeRecord.is_ignored.is_(False), TimeRecord.deleted_at.is_(None))
                .order_by(User.name, TimeRecord.record_datetime)
            )
            result = await session.execute(stmt)
            records = result.all()

            anomalies_list = await anomaly_service.get_anomalies(session, target_date, target_date)

            names = {user.id: user.name for _, user in records}
            names.update({a.user_id: a.user_name for a in anomalies_list})
            report_names = build_report_names(names)
            anomalies_descriptions = [f"{report_names[a.user_id]}: {a.description}" for a
                                      in anomalies_list]

            if not records:
                return template_service.get_daily_report_html(day_name, formatted_date, False, {},
                                                              anomalies_descriptions)

            user_activity = {}
            for record, user in records:
                short_name = report_names[user.id]
                if short_name not in user_activity:
                    user_activity[short_name] = []
                time_str = to_app_timezone(record.record_datetime).strftime("%H:%M")
                type_label = "E" if record.record_type == RecordType.ENTRY else "S"
                user_activity[short_name].append({"time": time_str, "type": type_label})

            return template_service.get_daily_report_html(day_name, formatted_date, True, user_activity,
                                                          anomalies_descriptions)
        except (ValueError, TypeError, AttributeError) as e:
            logger.exception(f'Erro HTML Report: {type(e).__name__}')
            return f"<p><em>Erro ao gerar relatório para {target_date}.</em></p>"


daily_report_service = DailyReportService()
