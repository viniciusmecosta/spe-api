from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.database.session import AsyncSessionLocal
from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.daily_summaries.daily_summary_events import schedule_days
from app.features.daily_summaries.daily_summary_exceptions import (
    DailySummaryUnavailableError,
)
from app.features.daily_summaries.daily_summary_models import DailySummary
from app.features.daily_summaries.daily_summary_repository import (
    daily_summary_repository,
)
from app.features.daily_summaries.daily_summary_schemas import DaySummaryValues
from app.features.holidays.holiday_models import Holiday
from app.features.payroll.payroll_models import PayrollClosure
from app.features.system.system_models import AuditLog
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import User
from app.shared.daily_excess_service import daily_excess_service
from app.shared.enums import AdjustmentStatus, AdjustmentType
from app.shared.time_calculation_service import (
    DailyAccountedResult,
    DailyTimeResult,
    PeriodTimeResult,
    time_calculation_service,
)


def from_legacy_period(day: date, result: PeriodTimeResult) -> DaySummaryValues:
    daily = result.daily_results[day]
    values = DaySummaryValues(
        worked_minutes=round(daily.gross_worked_seconds / 60),
        accounted_minutes=round(result.total_accounted_seconds / 60),
        expected_minutes=round(result.daily_expected_seconds[day] / 60),
        excess_minutes=round(result.total_excess_seconds / 60),
        authorized_excess_minutes=round(result.total_approved_excess_seconds / 60),
        missing_minutes=round(daily.missing_seconds / 60),
        waiver_minutes=round(daily.waiver_seconds / 60),
    )
    if any(value < 0 for value in vars(values).values()):
        raise ValueError(f"Negative apuration value for {day}")
    if values.authorized_excess_minutes > values.excess_minutes:
        raise ValueError(f"Authorized excess exceeds total excess for {day}")
    if values.accounted_minutes > values.worked_minutes:
        raise ValueError(f"Accounted time exceeds worked time for {day}")
    return values


class DailySummaryService:
    async def _load_period_rows(
        self, session: Any, user_id: int, first: date, last: date
    ) -> dict[date, DailySummary]:
        statement = select(DailySummary).where(
            DailySummary.user_id == user_id,
            DailySummary.apuration_date >= first,
            DailySummary.apuration_date <= last,
        )
        if hasattr(session, "sync_session"):
            rows = list((await session.scalars(statement)).all())
        else:
            rows = list(session.scalars(statement).all())
        return {row.apuration_date: row for row in rows}

    async def build_period(
        self, session: Any, user_id: int, first: date, last: date,
        records: list[TimeRecord], adjustments: list[AdjustmentRequest],
        holidays: list, historical_schedules: list,
    ) -> PeriodTimeResult:
        summaries = await self._load_period_rows(session, user_id, first, last)
        days = (last - first).days + 1
        if len(summaries) != days:
            all_days = {first + timedelta(days=offset) for offset in range(days)}
            schedule_days({(user_id, day) for day in all_days.difference(summaries)})
            raise DailySummaryUnavailableError()

        records_by_day: dict[date, list[TimeRecord]] = {}
        for record in records:
            records_by_day.setdefault(record.record_datetime.date(), []).append(record)
        adjustments_by_day: dict[date, list[AdjustmentRequest]] = {}
        for adjustment in adjustments:
            adjustments_by_day.setdefault(adjustment.target_date, []).append(adjustment)
        holiday_days = {holiday.date for holiday in holidays}

        daily_results = {}
        daily_accounted_results = {}
        daily_expected = {}
        daily_is_holiday = {}
        daily_waivers = {}
        total_gross = total_net = total_expected = total_waiver = 0
        total_unapproved = total_extra = total_missing = 0
        total_excess = total_approved = 0
        current = first
        while current <= last:
            row = summaries[current]
            day_records = sorted(
                records_by_day.get(current, []), key=lambda record: record.record_datetime
            )
            _, entries, exits, punches, blocks = time_calculation_service._process_records(
                day_records
            )
            gross = row.worked_minutes * 60
            net = row.accounted_minutes * 60
            expected = row.expected_minutes * 60
            waiver = row.waiver_minutes * 60
            unapproved = gross - net
            extra = max(0, net - expected) if historical_schedules else 0
            missing = row.missing_minutes * 60
            daily_results[current] = DailyTimeResult(
                raw_worked_seconds=gross,
                waiver_seconds=waiver,
                unapproved_extra_seconds=unapproved,
                net_worked_seconds=net,
                gross_worked_seconds=gross,
                extra_seconds=extra,
                missing_seconds=missing,
                entries=entries,
                exits=exits,
                punches=punches,
                punch_blocks=blocks,
            )
            daily_accounted_results[current] = DailyAccountedResult(
                raw_seconds=gross - waiver,
                excess_work_seconds=0,
                excess_lunch_seconds=0,
                early_return_seconds=0,
                total_excess_seconds=row.excess_minutes * 60,
                approved_seconds=row.authorized_excess_minutes * 60,
                accounted_seconds=net,
                has_schedule=expected > 0,
                has_lunch_rule=False,
            )
            daily_expected[current] = expected
            daily_is_holiday[current] = current in holiday_days
            daily_waivers[current] = next((
                adjustment for adjustment in adjustments_by_day.get(current, [])
                if adjustment.adjustment_type == AdjustmentType.WAIVER
                and adjustment.status == AdjustmentStatus.APPROVED
            ), None)
            total_gross += gross
            total_net += net
            total_expected += expected
            total_waiver += waiver
            total_unapproved += unapproved
            total_extra += extra
            total_missing += missing
            total_excess += row.excess_minutes * 60
            total_approved += row.authorized_excess_minutes * 60
            current += timedelta(days=1)

        return PeriodTimeResult(
            total_net_worked_seconds=total_net,
            total_gross_worked_seconds=total_gross,
            total_expected_seconds=total_expected,
            total_waiver_seconds=total_waiver,
            total_unapproved_extra_seconds=total_unapproved,
            total_extra_seconds=total_extra,
            total_missing_seconds=total_missing,
            final_balance_seconds=total_net - total_expected,
            daily_results=daily_results,
            daily_expected_seconds=daily_expected,
            daily_is_holiday=daily_is_holiday,
            daily_waivers=daily_waivers,
            total_accounted_seconds=total_net,
            total_excess_seconds=total_excess,
            total_approved_excess_seconds=total_approved,
        )

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


daily_summary_service = DailySummaryService()
daily_summary_recalculation_service = daily_summary_service
daily_summary_read_service = daily_summary_service
DailySummaryReadService = DailySummaryService
DailySummaryRecalculationService = DailySummaryService
