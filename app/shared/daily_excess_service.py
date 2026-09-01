import logging
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import get_async_session_context
from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.payroll.payroll_models import PayrollClosure
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


class DailyExcessService:
    def _create_daily_excess_adjustment(
        self, user_id: int, target_date: date, day_records: list[TimeRecord], accounted
    ) -> AdjustmentRequest | None:
        if accounted.total_excess_seconds <= 0:
            return None
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

        return AdjustmentRequest(
            user_id=user_id,
            adjustment_type=AdjustmentType.DAILY_EXCESS,
            target_date=target_date,
            time=exit_time,
            amount_hours=amount_hours,
            reason_text=reason,
            status=AdjustmentStatus.PENDING,
        )

    def _is_excess_applicable(self, schedule: UserWorkScheduleConfig | None, day_records: list) -> bool:
        return bool(
            schedule and
            getattr(schedule, 'is_daily_excess_enabled', False) and
            getattr(schedule, 'daily_hours', 0) > 0 and
            day_records
        )

    async def _evaluate_user_day_async(self, db: AsyncSession, user_id: int, target_date: date, tz: ZoneInfo):
        payroll_stmt = select(PayrollClosure).where(
            PayrollClosure.month == target_date.month,
            PayrollClosure.year == target_date.year,
            PayrollClosure.is_closed.is_(True),
            PayrollClosure.deleted_at.is_(None)
        )
        if await db.scalar(payroll_stmt):
            logger.info(f"Ignorando avaliacao de excedente: Folha fechada {target_date.month}/{target_date.year} (user_id={user_id})")
            return

        extra_time_stmt = select(AdjustmentRequest).where(
            AdjustmentRequest.user_id == user_id,
            AdjustmentRequest.target_date == target_date,
            AdjustmentRequest.adjustment_type == AdjustmentType.EXTRA_TIME,
            AdjustmentRequest.deleted_at.is_(None)
        )
        if await db.scalar(extra_time_stmt):
            logger.info(f"Ignorando avaliacao de excedente: Ja existe EXTRA_TIME para {target_date} (user_id={user_id})")
            return

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

        if self._is_excess_applicable(schedule, day_records):
            accounted = time_calculation_service.calculate_accounted_time(
                day_records=day_records,
                schedule=schedule,
                daily_excess_adj=None,
            )
            new_adj = self._create_daily_excess_adjustment(user_id, target_date, day_records, accounted)
            if new_adj:
                db.add(new_adj)

        for r in day_records:
            r.is_verified = True

    def _evaluate_user_day_sync(self, db: Session, user_id: int, target_date: date, tz: ZoneInfo):
        payroll_closed = db.query(PayrollClosure).filter(
            PayrollClosure.month == target_date.month,
            PayrollClosure.year == target_date.year,
            PayrollClosure.is_closed.is_(True),
            PayrollClosure.deleted_at.is_(None)
        ).first()
        if payroll_closed:
            logger.info(f"Ignorando avaliacao de excedente (sync): Folha fechada {target_date.month}/{target_date.year} (user_id={user_id})")
            return

        has_extra_time = db.query(AdjustmentRequest).filter(
            AdjustmentRequest.user_id == user_id,
            AdjustmentRequest.target_date == target_date,
            AdjustmentRequest.adjustment_type == AdjustmentType.EXTRA_TIME,
            AdjustmentRequest.deleted_at.is_(None)
        ).first()
        if has_extra_time:
            logger.info(f"Ignorando avaliacao de excedente (sync): Ja existe EXTRA_TIME para {target_date} (user_id={user_id})")
            return

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

        if self._is_excess_applicable(schedule, day_records):
            accounted = time_calculation_service.calculate_accounted_time(
                day_records=day_records,
                schedule=schedule,
                daily_excess_adj=None,
            )
            new_adj = self._create_daily_excess_adjustment(user_id, target_date, day_records, accounted)
            if new_adj:
                db.add(new_adj)

        for r in day_records:
            r.is_verified = True

    async def evaluate_user_day_async(self, db: AsyncSession, user_id: int, target_date: date):
        tz = ZoneInfo(settings.TIMEZONE)
        await self._evaluate_user_day_async(db, user_id, target_date, tz)

    def evaluate_user_day_sync(self, db: Session, user_id: int, target_date: date):
        tz = ZoneInfo(settings.TIMEZONE)
        self._evaluate_user_day_sync(db, user_id, target_date, tz)

    async def evaluate_user_day_bg(self, user_id: int, target_date: date):
        tz = ZoneInfo(settings.TIMEZONE)
        try:
            async with get_async_session_context() as db:
                await self._evaluate_user_day_async(db, user_id, target_date, tz)
        except Exception as e:
            logger.exception(f"Erro ao processar excedente em background para user_id={user_id} em {target_date}: {e}")

    async def evaluate_user_range_bg(self, user_id: int, start_date: date, end_date: date):
        tz = ZoneInfo(settings.TIMEZONE)
        try:
            async with get_async_session_context() as db:
                curr = start_date
                while curr <= end_date:
                    await self._evaluate_user_day_async(db, user_id, curr, tz)
                    curr += timedelta(days=1)
        except Exception as e:
            logger.exception(f"Erro ao reprocessar intervalo {start_date} a {end_date} para user_id={user_id}: {e}")


daily_excess_service = DailyExcessService()
