from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload

from app.database.payroll_lock import lock_payroll_periods

from app.core.config import settings
from app.database.session import AsyncSessionLocal
from app.features.adjustments.adjustment_models import AdjustmentRequest
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
from app.features.time_records.time_record_formatters import format_daily_records
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
        worked_minutes=daily.gross_worked_seconds / 60,
        accounted_minutes=result.total_accounted_seconds / 60,
        expected_minutes=result.daily_expected_seconds[day] / 60,
        excess_minutes=result.total_excess_seconds / 60,
        authorized_excess_minutes=result.total_approved_excess_seconds / 60,
        missing_minutes=daily.missing_seconds / 60,
        waiver_minutes=daily.waiver_seconds / 60,
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
        ).execution_options(populate_existing=True)
        if hasattr(session, "sync_session"):
            rows = list((await session.scalars(statement)).all())
        else:
            rows = list(session.scalars(statement).all())
        return {row.apuration_date: row for row in rows}

    @staticmethod
    def _requires_saved_summary(day_records, day_adjustments) -> bool:
        relevant_types = {
            AdjustmentType.FORGOT_PUNCH,
            AdjustmentType.PUNCH_NOT_COUNTED,
            AdjustmentType.DELETE_PUNCH,
            AdjustmentType.WAIVER,
            AdjustmentType.EXTRA_TIME,
            AdjustmentType.DAILY_EXCESS,
        }
        return bool(day_records) or any(
            adjustment.deleted_at is None
            and adjustment.status == AdjustmentStatus.APPROVED
            and adjustment.adjustment_type in relevant_types
            for adjustment in day_adjustments
        )

    @staticmethod
    def _expected_seconds(row, schedule, is_holiday: bool) -> int:
        if row is not None:
            return float(row.expected_minutes) * 60
        if schedule is not None and not is_holiday:
            return schedule.daily_hours * 3600
        return 0

    @staticmethod
    def _schedule_for_day(schedules, day: date):
        return next((
            item for item in schedules
            if item.day_of_week == day.weekday()
            and item.valid_from <= day
            and (item.valid_until is None or item.valid_until >= day)
        ), None)

    def _build_period_day(self, current, row, day_records, day_adjustments,
                          holiday_days, historical_schedules):
        if row is None and self._requires_saved_summary(day_records, day_adjustments):
            raise DailySummaryUnavailableError()
        entries, exits, punches, blocks = format_daily_records(day_records)
        is_holiday = current in holiday_days
        schedule = self._schedule_for_day(historical_schedules, current)
        expected = self._expected_seconds(row, schedule, is_holiday)
        gross = float(row.worked_minutes) * 60 if row is not None else 0
        net = float(row.accounted_minutes) * 60 if row is not None else 0
        waiver = float(row.waiver_minutes) * 60 if row is not None else 0
        unapproved = gross - net
        extra = max(0, net - expected) if historical_schedules else 0
        missing = float(row.missing_minutes) * 60 if row is not None else expected
        daily_result = DailyTimeResult(
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
        accounted_result = DailyAccountedResult(
            raw_seconds=gross - waiver,
            excess_work_seconds=0,
            excess_lunch_seconds=0,
            early_return_seconds=0,
            total_excess_seconds=float(row.excess_minutes) * 60 if row is not None else 0,
            approved_seconds=float(row.authorized_excess_minutes) * 60 if row is not None else 0,
            accounted_seconds=net,
            has_schedule=expected > 0,
            has_lunch_rule=False,
        )
        approved_waiver = next((
            adjustment for adjustment in day_adjustments
            if adjustment.adjustment_type == AdjustmentType.WAIVER
            and adjustment.status == AdjustmentStatus.APPROVED
        ), None)
        totals = (
            net, gross, expected, waiver, unapproved, extra, missing,
            float(row.excess_minutes) * 60 if row is not None else 0,
            float(row.authorized_excess_minutes) * 60 if row is not None else 0,
        )
        return daily_result, accounted_result, expected, is_holiday, approved_waiver, totals

    def _reset_excess(self, session, user_id: int, day: date) -> None:
        previous_excess = list((session.scalars(
            select(AdjustmentRequest).where(
                AdjustmentRequest.user_id == user_id,
                AdjustmentRequest.target_date == day,
                AdjustmentRequest.adjustment_type == AdjustmentType.DAILY_EXCESS,
                AdjustmentRequest.deleted_at.is_(None),
            )
        )).all())
        for adjustment in previous_excess:
            adjustment.deleted_at = datetime.now(timezone.utc)
            if adjustment.status in (AdjustmentStatus.APPROVED, AdjustmentStatus.REJECTED):
                session.add(AuditLog(
                    action="INVALIDATE_DAILY_EXCESS",
                    entity="ADJUSTMENT_REQUESTS",
                    entity_id=adjustment.id,
                    old_data={
                        "status": adjustment.status.value,
                        "amount_hours": adjustment.amount_hours,
                        "approved_amount_hours": adjustment.approved_amount_hours,
                    },
                    new_data={"reason": "SCHEDULE_CHANGED"},
                ))
        session.flush()
        daily_excess_service.evaluate_user_day_sync(
            session, user_id, day, overwrite_reviewed=True
        )
        session.flush()

    @staticmethod
    def _invalidate_reviewed_excess(session, reviewed, current_minutes: int) -> None:
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

    @staticmethod
    def _excess_is_current(existing_excess, current_minutes: int) -> bool:
        return (
            len(existing_excess) == 1
            and round((existing_excess[0].amount_hours or 0) * 60) == current_minutes
        ) or (not existing_excess and current_minutes == 0)

    def _refresh_excess(self, session, user_id, day, records, holidays,
                              historical_schedules, adjustments, period):
        reviewed = [
            adjustment for adjustment in adjustments
            if adjustment.adjustment_type == AdjustmentType.DAILY_EXCESS
            and adjustment.status in (AdjustmentStatus.APPROVED, AdjustmentStatus.REJECTED)
        ]
        current_minutes = round(period.total_excess_seconds / 60)
        changed_reviewed_value = (
            reviewed
            and round((reviewed[0].amount_hours or 0) * 60) != current_minutes
        )
        if changed_reviewed_value:
            self._invalidate_reviewed_excess(session, reviewed, current_minutes)
            session.flush()

        existing_excess = [
            adjustment for adjustment in adjustments
            if adjustment.adjustment_type == AdjustmentType.DAILY_EXCESS
            and adjustment.deleted_at is None
        ]
        if self._excess_is_current(existing_excess, current_minutes):
            return adjustments, period
        daily_excess_service.evaluate_user_day_sync(session, user_id, day)
        session.flush()
        adjustments = list((session.scalars(
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
            historical_schedules=historical_schedules,
        )
        return adjustments, period

    async def build_period(
        self, session: Any, user_id: int, first: date, last: date,
        records: list[TimeRecord], adjustments: list[AdjustmentRequest],
        holidays: list, historical_schedules: list,
    ) -> PeriodTimeResult:
        summaries = await self._load_period_rows(session, user_id, first, last)

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
            row = summaries.get(current)
            day_records = sorted(
                records_by_day.get(current, []), key=lambda record: record.record_datetime
            )
            day_adjustments = adjustments_by_day.get(current, [])
            result, accounted, expected, is_holiday, daily_waiver, totals = self._build_period_day(
                current, row, day_records, day_adjustments, holiday_days, historical_schedules
            )
            daily_results[current] = result
            daily_accounted_results[current] = accounted
            daily_expected[current] = expected
            daily_is_holiday[current] = is_holiday
            daily_waivers[current] = daily_waiver
            (day_net, day_gross, day_expected, day_waiver, day_unapproved,
             day_extra, day_missing, day_excess, day_approved) = totals
            total_net += day_net
            total_gross += day_gross
            total_expected += day_expected
            total_waiver += day_waiver
            total_unapproved += day_unapproved
            total_extra += day_extra
            total_missing += day_missing
            total_excess += day_excess
            total_approved += day_approved
            current += timedelta(days=1)

        return PeriodTimeResult(
            total_net_worked_seconds=total_net,
            total_gross_worked_seconds=total_gross,
            total_expected_seconds=total_expected,
            total_waiver_seconds=total_waiver,
            total_unapproved_extra_seconds=total_unapproved,
            total_extra_seconds=total_extra,
            total_missing_seconds=total_missing,
            final_balance_seconds=total_extra - total_missing,
            daily_results=daily_results,
            daily_expected_seconds=daily_expected,
            daily_is_holiday=daily_is_holiday,
            daily_waivers=daily_waivers,
            total_accounted_seconds=total_net,
            total_excess_seconds=total_excess,
            total_approved_excess_seconds=total_approved,
            daily_accounted_results=daily_accounted_results,
        )

    def _calculate_user_day(
        self,
        session: Session,
        user_id: int,
        day: date,
        refresh_excess: bool,
        reset_excess: bool = False,
    ) -> None:
        user = session.scalar(
            select(User)
            .options(selectinload(User.historical_schedules))
            .where(User.id == user_id)
            .execution_options(populate_existing=True)
        )
        if user is None:
            return

        if reset_excess:
            self._reset_excess(session, user_id, day)

        timezone_local = ZoneInfo(settings.TIMEZONE)
        first = datetime.combine(day, time.min, tzinfo=timezone_local)
        last = first + timedelta(days=1)
        records = list((session.scalars(
            select(TimeRecord)
            .where(
                TimeRecord.user_id == user_id,
                TimeRecord.record_datetime >= first,
                TimeRecord.record_datetime < last,
                TimeRecord.deleted_at.is_(None),
                TimeRecord.is_ignored.is_(False),
            )
            .order_by(TimeRecord.record_datetime)
            .execution_options(populate_existing=True)
        )).all())
        adjustments = list((session.scalars(
            select(AdjustmentRequest).where(
                AdjustmentRequest.user_id == user_id,
                AdjustmentRequest.target_date == day,
                AdjustmentRequest.deleted_at.is_(None),
            )
            .execution_options(populate_existing=True)
        )).all())
        holidays = list((session.scalars(
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

        if not reset_excess and refresh_excess:
            adjustments, period = self._refresh_excess(
                session, user_id, day, records, holidays,
                user.historical_schedules, adjustments, period,
            )
        daily_summary_repository.upsert_sync(
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
                await session.run_sync(
                    lambda db: self.calculate_in_session(
                        db, user_id, day, refresh_excess, allow_closed, reset_excess
                    )
                )

    def calculate_in_session(
        self, session: Session, user_id: int, day: date,
        refresh_excess: bool = True, allow_closed: bool = False,
        reset_excess: bool = False,
    ) -> None:
        lock_payroll_periods(session, {(day.year, day.month)})
        if session.scalar(select(User.id).where(User.id == user_id)) is None:
            return
        if not allow_closed:
            closed_period = session.scalar(
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
        session.execute(
            insert(table).values(user_id=user_id, apuration_date=day)
            .on_conflict_do_nothing(constraint="uq_daily_summaries_user_date")
        )
        session.scalar(
            select(DailySummary.id).where(
                DailySummary.user_id == user_id, DailySummary.apuration_date == day,
            ).with_for_update()
        )
        self._calculate_user_day(
            session, user_id, day, refresh_excess, reset_excess=reset_excess
        )


daily_summary_service = DailySummaryService()
daily_summary_recalculation_service = daily_summary_service
daily_summary_read_service = daily_summary_service
DailySummaryReadService = DailySummaryService
DailySummaryRecalculationService = DailySummaryService
