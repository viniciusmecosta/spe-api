import asyncio
import inspect
import logging
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.reports.template_service import template_service
from app.features.time_records.time_record_models import TimeRecord
from app.features.timesheets.anomaly_service import anomaly_service
from app.features.users.user_models import User
from app.shared import deps
from app.shared.enums import DayOfWeek, RecordType
from app.utils.formatters import format_short_name

logger = logging.getLogger(__name__)


class DailyReportService:
    def __init__(self, db: Annotated[Any, Depends(deps.get_async_db)] = None):
        self.db = db

    def generate_daily_report_html(self, db: Any | None = None, target_date: date | None = None) -> str:
        session = db if db is not None else self.db
        assert session is not None
        assert target_date is not None
        try:
            formatted_date = target_date.strftime("%d/%m/%Y")
            day_name = DayOfWeek(target_date.weekday()).nome

            start_local = datetime.combine(target_date, datetime.min.time())
            end_local = datetime.combine(target_date, datetime.max.time())

            records = (
                session.query(TimeRecord, User)
                .join(User, TimeRecord.user_id == User.id)
                .filter(TimeRecord.record_datetime >= start_local)
                .filter(TimeRecord.record_datetime <= end_local)
                .filter(TimeRecord.is_ignored == False)
                .order_by(User.name, TimeRecord.record_datetime)
                .all()
            )
            raw_anomalies = anomaly_service.get_anomalies(session, target_date, target_date)
            if inspect.isawaitable(raw_anomalies):
                try:
                    loop = asyncio.get_running_loop()
                    if loop.is_running():
                        anomalies_list = []
                    else:
                        anomalies_list = loop.run_until_complete(raw_anomalies)
                except RuntimeError:
                    anomalies_list = asyncio.run(raw_anomalies)
            else:
                anomalies_list = raw_anomalies

            anomalies_descriptions = [f"<strong>{format_short_name(a.user_name)}</strong>: {a.description}" for a
                                      in anomalies_list]

            if not records:
                return template_service.get_daily_report_html(day_name, formatted_date, False, {},
                                                              anomalies_descriptions)

            user_activity = {}
            for record, user in records:
                short_name = format_short_name(user.name)
                if short_name not in user_activity:
                    user_activity[short_name] = []
                time_str = record.record_datetime.strftime("%H:%M")
                type_label = "E" if record.record_type == RecordType.ENTRY else "S"
                user_activity[short_name].append({"time": time_str, "type": type_label})

            return template_service.get_daily_report_html(day_name, formatted_date, True, user_activity,
                                                          anomalies_descriptions)
        except (ValueError, TypeError, AttributeError) as e:
            logger.exception(f"Erro HTML Report: {e}")
            return f"<p><em>Erro ao gerar relatório para {target_date}.</em></p>"


daily_report_service = DailyReportService()
