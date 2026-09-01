import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import get_db_session
from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import UserWorkScheduleConfig
from app.shared.enums import (
    AdjustmentStatus,
    AdjustmentType,
    DayOfWeek,
    RecordType,
)
from app.shared.time_calculation_service import time_calculation_service

logger = logging.getLogger(__name__)


class DailyExcessCronService:
    def process_daily_excess(self):
        tz = ZoneInfo(settings.TIMEZONE)
        try:
            with get_db_session() as db:
                self._process_unverified_days_sync(db, tz)
                db.commit()
        except SQLAlchemyError as e:
            logger.exception(f"Erro ao processar excedente diario no banco: {e}")
        except Exception as e:
            logger.exception(f"Erro inesperado ao processar excedente diario: {e}")

    def _process_unverified_days_sync(self, db: Session, tz: ZoneInfo):
        unverified_records = db.query(TimeRecord).filter(
            TimeRecord.is_verified.is_(False),
            TimeRecord.deleted_at.is_(None),
            TimeRecord.is_ignored.is_(False),
        ).all()

        if not unverified_records:
            return

        user_dates = {
            (r.user_id, r.record_datetime.date())
            for r in unverified_records
        }

        for user_id, target_date in user_dates:
            try:
                self._evaluate_user_day_sync(db, user_id, target_date, tz)
            except Exception as e:
                logger.exception(f"Erro ao avaliar excedente para user_id={user_id} em {target_date}: {e}")

    def _evaluate_user_day_sync(self, db: Session, user_id: int, target_date, tz: ZoneInfo):
        start_of_day = datetime.combine(target_date, time.min, tzinfo=tz)
        end_of_day = datetime.combine(target_date, time.max, tzinfo=tz)

        day_records = db.query(TimeRecord).filter(
            TimeRecord.user_id == user_id,
            TimeRecord.record_datetime >= start_of_day,
            TimeRecord.record_datetime <= end_of_day,
            TimeRecord.deleted_at.is_(None),
            TimeRecord.is_ignored.is_(False),
        ).order_by(TimeRecord.record_datetime.asc()).all()

        target_day = DayOfWeek.from_date(target_date)
        schedule = db.query(UserWorkScheduleConfig).filter(
            UserWorkScheduleConfig.user_id == user_id,
            UserWorkScheduleConfig.day_of_week == target_day.value,
            UserWorkScheduleConfig.valid_from <= target_date,
            (UserWorkScheduleConfig.valid_until.is_(None) | (UserWorkScheduleConfig.valid_until >= target_date)),
        ).order_by(UserWorkScheduleConfig.valid_from.desc()).first()

        existing_adjustments = db.query(AdjustmentRequest).filter(
            AdjustmentRequest.user_id == user_id,
            AdjustmentRequest.target_date == target_date,
            AdjustmentRequest.adjustment_type == AdjustmentType.DAILY_EXCESS,
            AdjustmentRequest.deleted_at.is_(None),
        ).all()
        for adj in existing_adjustments:
            db.delete(adj)

        if schedule and getattr(schedule, 'daily_hours', 0) > 0 and day_records:
            accounted = time_calculation_service.calculate_accounted_time(
                day_records=day_records,
                schedule=schedule,
                daily_excess_adj=None,
            )

            if accounted.total_excess_seconds > 0:
                last_exit = next(
                    (r for r in reversed(day_records) if r.record_type == RecordType.EXIT),
                    None
                )
                exit_time = last_exit.record_datetime.time() if last_exit else None

                excess_mins_work = int(accounted.excess_work_seconds / 60)
                excess_mins_lunch = int(accounted.excess_lunch_seconds / 60)
                parts = []
                if excess_mins_work > 0:
                    parts.append(f"{excess_mins_work}min de jornada excedente")
                if excess_mins_lunch > 0:
                    parts.append(f"{excess_mins_lunch}min de almoço excedido")
                reason = "Excedente automático detectado: " + ", ".join(parts)
                amount_hours = round(accounted.total_excess_seconds / 3600.0, 4)

                new_adj = AdjustmentRequest(
                    user_id=user_id,
                    adjustment_type=AdjustmentType.DAILY_EXCESS,
                    target_date=target_date,
                    time=exit_time,
                    amount_hours=amount_hours,
                    reason_text=reason,
                    status=AdjustmentStatus.PENDING,
                )
                db.add(new_adj)

        for r in day_records:
            r.is_verified = True

    async def async_process_daily_excess(self, db: AsyncSession):
        tz = ZoneInfo(settings.TIMEZONE)
        unverified_stmt = select(TimeRecord).where(
            TimeRecord.is_verified.is_(False),
            TimeRecord.deleted_at.is_(None),
            TimeRecord.is_ignored.is_(False),
        )
        res = await db.scalars(unverified_stmt)
        unverified_records = list(res.all())

        if not unverified_records:
            return

        user_dates = {
            (r.user_id, r.record_datetime.date())
            for r in unverified_records
        }

        for user_id, target_date in user_dates:
            try:
                await self._evaluate_user_day_async(db, user_id, target_date, tz)
            except Exception as e:
                logger.exception(f"Erro assincrono ao avaliar excedente para user_id={user_id} em {target_date}: {e}")
        await db.commit()

    async def _evaluate_user_day_async(self, db: AsyncSession, user_id: int, target_date, tz: ZoneInfo):
        start_of_day = datetime.combine(target_date, time.min, tzinfo=tz)
        end_of_day = datetime.combine(target_date, time.max, tzinfo=tz)

        rec_stmt = select(TimeRecord).where(
            TimeRecord.user_id == user_id,
            TimeRecord.record_datetime >= start_of_day,
            TimeRecord.record_datetime <= end_of_day,
            TimeRecord.deleted_at.is_(None),
            TimeRecord.is_ignored.is_(False),
        ).order_by(TimeRecord.record_datetime.asc())
        day_records = list((await db.scalars(rec_stmt)).all())

        target_day = DayOfWeek.from_date(target_date)
        sched_stmt = select(UserWorkScheduleConfig).where(
            UserWorkScheduleConfig.user_id == user_id,
            UserWorkScheduleConfig.day_of_week == target_day.value,
            UserWorkScheduleConfig.valid_from <= target_date,
            (UserWorkScheduleConfig.valid_until.is_(None) | (UserWorkScheduleConfig.valid_until >= target_date)),
        ).order_by(UserWorkScheduleConfig.valid_from.desc())
        schedule = await db.scalar(sched_stmt)

        adj_stmt = select(AdjustmentRequest).where(
            AdjustmentRequest.user_id == user_id,
            AdjustmentRequest.target_date == target_date,
            AdjustmentRequest.adjustment_type == AdjustmentType.DAILY_EXCESS,
            AdjustmentRequest.deleted_at.is_(None),
        )
        existing_adjustments = list((await db.scalars(adj_stmt)).all())
        for adj in existing_adjustments:
            await db.delete(adj)

        if schedule and getattr(schedule, 'daily_hours', 0) > 0 and day_records:
            accounted = time_calculation_service.calculate_accounted_time(
                day_records=day_records,
                schedule=schedule,
                daily_excess_adj=None,
            )

            if accounted.total_excess_seconds > 0:
                last_exit = next(
                    (r for r in reversed(day_records) if r.record_type == RecordType.EXIT),
                    None
                )
                exit_time = last_exit.record_datetime.time() if last_exit else None

                excess_mins_work = int(accounted.excess_work_seconds / 60)
                excess_mins_lunch = int(accounted.excess_lunch_seconds / 60)
                parts = []
                if excess_mins_work > 0:
                    parts.append(f"{excess_mins_work}min de jornada excedente")
                if excess_mins_lunch > 0:
                    parts.append(f"{excess_mins_lunch}min de almoço excedido")
                reason = "Excedente automático detectado: " + ", ".join(parts)
                amount_hours = round(accounted.total_excess_seconds / 3600.0, 4)

                new_adj = AdjustmentRequest(
                    user_id=user_id,
                    adjustment_type=AdjustmentType.DAILY_EXCESS,
                    target_date=target_date,
                    time=exit_time,
                    amount_hours=amount_hours,
                    reason_text=reason,
                    status=AdjustmentStatus.PENDING,
                )
                db.add(new_adj)

        for r in day_records:
            r.is_verified = True

    async def evaluate_user_day_async(self, db: AsyncSession, user_id: int, target_date):
        tz = ZoneInfo(settings.TIMEZONE)
        await self._evaluate_user_day_async(db, user_id, target_date, tz)

    def evaluate_user_day_sync(self, db: Session, user_id: int, target_date):
        tz = ZoneInfo(settings.TIMEZONE)
        self._evaluate_user_day_sync(db, user_id, target_date, tz)


daily_excess_cron_service = DailyExcessCronService()
