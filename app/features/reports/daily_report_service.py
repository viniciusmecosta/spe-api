import logging
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.domain.enums import DayOfWeek, RecordType
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import User
from app.features.reports.template_service import template_service
from app.features.timesheets.anomaly_service import anomaly_service
from app.utils.formatters import format_short_name

logger = logging.getLogger(__name__)


class DailyReportService:
    def generate_daily_report_html(self, db: Session, target_date: date) -> str:
        try:
            formatted_date = target_date.strftime("%d/%m/%Y")
            day_name = DayOfWeek(target_date.weekday()).nome

            start_local = datetime.combine(target_date, datetime.min.time())
            end_local = datetime.combine(target_date, datetime.max.time())

            records = (
                db.query(TimeRecord, User)
                .join(User, TimeRecord.user_id == User.id)
                .filter(TimeRecord.record_datetime >= start_local)
                .filter(TimeRecord.record_datetime <= end_local)
                .filter(TimeRecord.is_ignored == False)
                .order_by(User.name, TimeRecord.record_datetime)
                .all()
            )

            anomalies_list = anomaly_service.get_anomalies(db, target_date, target_date)
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
