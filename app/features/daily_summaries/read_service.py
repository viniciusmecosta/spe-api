from datetime import date, timedelta
from typing import Any

from sqlalchemy import select

from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.daily_summaries.dispatch import schedule_days
from app.features.daily_summaries.models import DailySummary
from app.features.time_records.time_record_models import TimeRecord
from app.shared.enums import AdjustmentStatus, AdjustmentType
from app.shared.time_calculation_service import (
    DailyAccountedResult,
    DailyTimeResult,
    PeriodTimeResult,
    time_calculation_service,
)


class DailySummaryUnavailableError(Exception):
    pass


class DailySummaryReadService:
    async def _load(
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
        summaries = await self._load(session, user_id, first, last)
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


daily_summary_read_service = DailySummaryReadService()
