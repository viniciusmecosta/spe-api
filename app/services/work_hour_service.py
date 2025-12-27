from datetime import datetime, date, timedelta

import pytz
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.models.enums import RecordType
from app.repositories.time_record_repository import time_record_repository
from app.repositories.user_repository import user_repository
from app.schemas.work_hour import WorkHourBalanceResponse


class WorkHourService:
    def calculate_balance(self, db: Session, user_id: int, start_date: date, end_date: date) -> WorkHourBalanceResponse:
        tz = pytz.timezone(settings.TIMEZONE)

        start_dt = tz.localize(datetime.combine(start_date, datetime.min.time()))
        end_dt = tz.localize(datetime.combine(end_date, datetime.max.time()))

        records = time_record_repository.get_by_range(db, user_id, start_dt, end_dt)
        user = user_repository.get(db, user_id)

        total_seconds = 0.0
        entry_time = None

        for record in records:
            if record.record_type == RecordType.ENTRY:
                entry_time = record.record_datetime
            elif record.record_type == RecordType.EXIT and entry_time:
                delta = record.record_datetime - entry_time
                total_seconds += delta.total_seconds()
                entry_time = None

        total_worked_hours = total_seconds / 3600.0

        expected_hours = 0.0
        current_date = start_date
        daily_workload = user.weekly_workload_hours / 5.0

        while current_date <= end_date:
            if current_date.weekday() < 5:
                expected_hours += daily_workload
            current_date += timedelta(days=1)

        balance = total_worked_hours - expected_hours

        return WorkHourBalanceResponse(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            total_worked_hours=round(total_worked_hours, 2),
            expected_hours=round(expected_hours, 2),
            balance_hours=round(balance, 2)
        )


work_hour_service = WorkHourService()
