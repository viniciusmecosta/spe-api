from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.holiday_repository import holiday_repository
from app.repositories.time_record_repository import time_record_repository
from app.repositories.user_repository import user_repository
from app.schemas.work_hour import WorkHourBalanceResponse
from app.domain.models.enums import DayOfWeek

class WorkHourService:
    def calculate_balance(self, db: Session, user_id: int, start_date: date, end_date: date) -> WorkHourBalanceResponse:
        tz = ZoneInfo(settings.TIMEZONE)

        start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=tz)
        end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=tz)

        records = time_record_repository.get_by_range(db, user_id, start_dt, end_dt)
        user = user_repository.get(db, user_id)
        holidays = holiday_repository.get_all(db)

        from app.domain.models.adjustment import AdjustmentRequest
        from app.domain.models.enums import AdjustmentStatus, AdjustmentType

        adjustments = db.query(AdjustmentRequest).filter(
            AdjustmentRequest.user_id == user_id,
            AdjustmentRequest.target_date >= start_date,
            AdjustmentRequest.target_date <= end_date,
            AdjustmentRequest.status == AdjustmentStatus.APPROVED,
            AdjustmentRequest.deleted_at.is_(None)
        ).all()

        unapproved_extra_adjs = db.query(AdjustmentRequest).filter(
            AdjustmentRequest.user_id == user_id,
            AdjustmentRequest.target_date >= start_date,
            AdjustmentRequest.target_date <= end_date,
            AdjustmentRequest.adjustment_type == AdjustmentType.EXTRA_TIME,
            AdjustmentRequest.status.in_([AdjustmentStatus.PENDING, AdjustmentStatus.REJECTED]),
            AdjustmentRequest.deleted_at.is_(None)
        ).all()

        has_schedule = bool(user.historical_schedules)

        total_seconds = 0.0
        expected_hours = 0.0
        current_date = start_date

        from app.services.time_calculation_service import time_calculation_service

        while current_date <= end_date:
            day_records = [r for r in records if r.record_datetime.date() == current_date]
            day_records.sort(key=lambda x: x.record_datetime)

            is_holiday = any(h.date == current_date for h in holidays)

            day_expected_hours = 0.0
            if not is_holiday and has_schedule:
                target_day = DayOfWeek.from_date(current_date)
                valid_schedules = [
                    s for s in user.historical_schedules
                    if s.valid_from <= current_date and (s.valid_until is None or s.valid_until >= current_date)
                ]
                schedule = next((s for s in valid_schedules if s.day_of_week == target_day.value), None)

                if schedule:
                    day_expected_hours = schedule.daily_hours
                    expected_hours += schedule.daily_hours

            abono = next((adj for adj in adjustments if
                          adj.target_date == current_date and adj.adjustment_type == AdjustmentType.WAIVER), None)

            day_unapproved_extras = [adj for adj in unapproved_extra_adjs if adj.target_date == current_date]

            time_result = time_calculation_service.calculate_daily_time(
                day_records=day_records,
                expected_seconds=day_expected_hours * 3600,
                waiver_adj=abono,
                unapproved_extra_adjs=day_unapproved_extras,
                is_excused=bool(abono)
            )

            total_seconds += time_result.net_worked_seconds

            current_date += timedelta(days=1)

        total_worked_hours = total_seconds / 3600.0

        if not has_schedule:
            balance = 0.0
        else:
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
