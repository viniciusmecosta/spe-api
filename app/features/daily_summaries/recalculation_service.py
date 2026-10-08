from datetime import date, datetime, time, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.database.session import AsyncSessionLocal
from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.daily_summaries.calculator import from_legacy_period
from app.features.daily_summaries.models import DailySummary
from app.features.daily_summaries.repository import daily_summary_repository
from app.features.holidays.holiday_models import Holiday
from app.features.payroll.payroll_models import PayrollClosure
from app.features.system.system_models import AuditLog
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import User
from app.shared.daily_excess_service import daily_excess_service
from app.shared.enums import AdjustmentStatus, AdjustmentType
from app.shared.time_calculation_service import time_calculation_service


class DailySummaryRecalculationService:
    async def _calculate_user_day(
        self,
        session: AsyncSession,
        user_id: int,
        day: date,
        refresh_excess: bool,
        reset_excess: bool = False,
    ) -> None:
        user = await session.scalar(
            select(User)
            .options(selectinload(User.historical_schedules))
            .where(User.id == user_id)
        )
        if user is None:
            return

        if reset_excess:
            await daily_excess_service.evaluate_user_day_async(
                session, user_id, day, overwrite_reviewed=True
            )
            await session.flush()

        timezone_local = ZoneInfo(settings.TIMEZONE)
        first = datetime.combine(day, time.min, tzinfo=timezone_local)
        last = first + timedelta(days=1)
        records = list((await session.scalars(
            select(TimeRecord)
            .where(
                TimeRecord.user_id == user_id,
                TimeRecord.record_datetime >= first,
                TimeRecord.record_datetime < last,
                TimeRecord.deleted_at.is_(None),
                TimeRecord.is_ignored.is_(False),
            )
            .order_by(TimeRecord.record_datetime)
        )).all())
        adjustments = list((await session.scalars(
            select(AdjustmentRequest).where(
                AdjustmentRequest.user_id == user_id,
                AdjustmentRequest.target_date == day,
                AdjustmentRequest.deleted_at.is_(None),
            )
        )).all())
        holidays = list((await session.scalars(
            select(Holiday).where(Holiday.date == day)
        )).all())
        period = time_calculation_service.calculate_period_time(
            start_date=day,
            end_date=day,
            records=records,
            adjustments=adjustments,
            holidays=holidays,
            historical_schedules=user.historical_schedules,
        )

        if not reset_excess:
            reviewed = [
                adjustment for adjustment in adjustments
                if adjustment.adjustment_type == AdjustmentType.DAILY_EXCESS
                and adjustment.status in (AdjustmentStatus.APPROVED, AdjustmentStatus.REJECTED)
            ]
            current_minutes = round(period.total_excess_seconds / 60)
            if reviewed and refresh_excess:
                previous_minutes = round((reviewed[0].amount_hours or 0) * 60)
                if current_minutes != previous_minutes:
                    for adjustment in reviewed:
                        adjustment.deleted_at = datetime.now(timezone.utc)
                        session.add(AuditLog(
                            action="INVALIDATE_DAILY_EXCESS",
                            entity="ADJUSTMENT_REQUESTS",
                            entity_id=adjustment.id,
                            old_data={
                                "status": adjustment.status.value,
                                "amount_hours": adjustment.amount_hours,
                                "approved_amount_hours": adjustment.approved_amount_hours,
                            },
                            new_data={"recalculated_minutes": current_minutes},
                        ))
                    await session.flush()

            existing_excess = [
                adjustment for adjustment in adjustments
                if adjustment.adjustment_type == AdjustmentType.DAILY_EXCESS
                and adjustment.deleted_at is None
            ]
            excess_is_current = (
                len(existing_excess) == 1
                and round((existing_excess[0].amount_hours or 0) * 60) == current_minutes
            ) or (not existing_excess and current_minutes == 0)
            if refresh_excess and not excess_is_current:
                await daily_excess_service.evaluate_user_day_async(session, user_id, day)
                await session.flush()
                adjustments = list((await session.scalars(
                    select(AdjustmentRequest).where(
                        AdjustmentRequest.user_id == user_id,
                        AdjustmentRequest.target_date == day,
                        AdjustmentRequest.deleted_at.is_(None),
                    )
                )).all())
                period = time_calculation_service.calculate_period_time(
                    start_date=day,
                    end_date=day,
                    records=records,
                    adjustments=adjustments,
                    holidays=holidays,
                    historical_schedules=user.historical_schedules,
                )
        await daily_summary_repository.upsert(
            session, user_id, day, from_legacy_period(day, period)
        )

    async def recalculate_day(
        self, user_id: int, day: date, reset_excess: bool = False
    ) -> None:
        await self.calculate_day(
            user_id, day, refresh_excess=True, allow_closed=False, reset_excess=reset_excess
        )

    async def calculate_day(
        self,
        user_id: int,
        day: date,
        refresh_excess: bool,
        allow_closed: bool,
        reset_excess: bool = False,
    ) -> None:
        async with AsyncSessionLocal() as session:
            session.sync_session.info["skip_daily_summary_tracking"] = True
            async with session.begin():
                if await session.scalar(select(User.id).where(User.id == user_id)) is None:
                    return
                if not allow_closed:
                    closed_period = await session.scalar(
                        select(PayrollClosure.id).where(
                            PayrollClosure.year == day.year,
                            PayrollClosure.month == day.month,
                            PayrollClosure.is_closed.is_(True),
                            PayrollClosure.deleted_at.is_(None),
                        ).limit(1)
                    )
                    if closed_period is not None:
                        return
                table = DailySummary.__table__
                await session.execute(
                    insert(table)
                    .values(user_id=user_id, apuration_date=day)
                    .on_conflict_do_nothing(
                        constraint="uq_daily_summaries_user_date"
                    )
                )
                await session.scalar(
                    select(DailySummary.id)
                    .where(
                        DailySummary.user_id == user_id,
                        DailySummary.apuration_date == day,
                    )
                    .with_for_update()
                )
                await self._calculate_user_day(
                    session, user_id, day, refresh_excess, reset_excess=reset_excess
                )

daily_summary_recalculation_service = DailySummaryRecalculationService()
