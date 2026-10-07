import importlib
import logging
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import exists, extract, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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


logger = logging.getLogger(__name__)


class DailySummaryRecalculationService:
    async def _calculate_user_day(
        self, session: AsyncSession, user_id: int, day: date, refresh_excess: bool
    ) -> None:
        user = await session.scalar(
            select(User)
            .options(selectinload(User.historical_schedules))
            .where(User.id == user_id)
        )
        if user is None:
            return

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

    async def _process_row(
        self, session: AsyncSession, summary: DailySummary, refresh_excess: bool
    ) -> None:
        await self._calculate_user_day(
            session, summary.user_id, summary.apuration_date, refresh_excess
        )

    async def recalculate_day(self, user_id: int, day: date) -> None:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                summary = await session.scalar(
                    select(DailySummary)
                    .where(
                        DailySummary.user_id == user_id,
                        DailySummary.apuration_date == day,
                    )
                    .with_for_update()
                )
                if summary is None or not summary.pending_recalculation:
                    return
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
                await self._process_row(session, summary, refresh_excess=True)

    async def run_once(
        self, allow_closed: bool = False,
        first_day: date | None = None,
        last_day: date | None = None,
    ) -> bool:
        importlib.import_module("app.features.companies.company_models")
        importlib.import_module("app.features.printers.printer_models")
        importlib.import_module("app.features.devices.device_models")
        failed_error = None
        async with AsyncSessionLocal() as session:
            async with session.begin():
                query = select(DailySummary).where(
                    DailySummary.pending_recalculation.is_(True)
                )
                if first_day is not None:
                    query = query.where(DailySummary.apuration_date >= first_day)
                if last_day is not None:
                    query = query.where(DailySummary.apuration_date <= last_day)
                if not allow_closed:
                    closed_period = exists(
                        select(PayrollClosure.id).where(
                            PayrollClosure.year == extract("year", DailySummary.apuration_date),
                            PayrollClosure.month == extract("month", DailySummary.apuration_date),
                            PayrollClosure.is_closed.is_(True),
                            PayrollClosure.deleted_at.is_(None),
                        )
                    )
                    query = query.where(~closed_period)
                summary = await session.scalar(
                    query.order_by(DailySummary.apuration_date, DailySummary.user_id)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                if summary is None:
                    return False
                try:
                    async with session.begin_nested():
                        await self._process_row(session, summary, refresh_excess=not allow_closed)
                except Exception as error:
                    summary.updated_at = datetime.now(timezone.utc)
                    failed_error = error
                    logger.exception(
                        "Daily summary recalculation failed for user %s on %s",
                        summary.user_id, summary.apuration_date,
                    )
        if failed_error is not None:
            raise RuntimeError("Daily summary recalculation failed") from failed_error
        return True

daily_summary_recalculation_service = DailySummaryRecalculationService()
