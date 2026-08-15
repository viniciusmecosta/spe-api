from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.time_records.time_record_models import TimeRecord
from app.shared.enums import (
    AdjustmentStatus,
    AdjustmentType,
    DayOfWeek,
    RecordType,
)


@dataclass
class DailyTimeResult:
    raw_worked_seconds: float
    waiver_seconds: float
    unapproved_extra_seconds: float
    net_worked_seconds: float
    gross_worked_seconds: float
    extra_seconds: float
    missing_seconds: float
    entries: list[str]
    exits: list[str]
    punches: list[str]
    punch_blocks: list[str]


@dataclass
class PeriodTimeResult:
    total_net_worked_seconds: float
    total_gross_worked_seconds: float
    total_expected_seconds: float
    total_waiver_seconds: float
    total_unapproved_extra_seconds: float
    total_extra_seconds: float
    total_missing_seconds: float
    final_balance_seconds: float
    daily_results: dict[date, DailyTimeResult]
    daily_expected_seconds: dict[date, float]
    daily_is_holiday: dict[date, bool]
    daily_waivers: dict[date, AdjustmentRequest | None]


class _DailyProcessState:
    def __init__(self):
        self.entries: list[str] = []
        self.exits: list[str] = []
        self.punches: list[str] = []
        self.punch_blocks: list[str] = []
        self.worked_seconds: float = 0.0
        self.entry_time: datetime | None = None

    def handle_record(self, rec: TimeRecord):
        time_str = rec.record_datetime.strftime("%H:%M")
        is_entry = rec.record_type == RecordType.ENTRY

        self.punches.append(f"{time_str} {'(E)' if is_entry else '(S)'}")

        if is_entry:
            self._handle_entry(rec, time_str)
        else:
            self._handle_exit(rec, time_str)

    def _handle_entry(self, rec: TimeRecord, time_str: str):
        self.entries.append(time_str)
        if self.entry_time is not None:
            self.punch_blocks.append(f"{self.entry_time.strftime('%H:%M')} - --:--")
        self.entry_time = rec.record_datetime.replace(second=0, microsecond=0)

    def _handle_exit(self, rec: TimeRecord, time_str: str):
        self.exits.append(time_str)
        if self.entry_time is None:
            self.punch_blocks.append(f"--:-- - {time_str}")
            return

        delta = rec.record_datetime.replace(second=0, microsecond=0) - self.entry_time
        seconds = delta.total_seconds()

        if seconds <= 86400:
            self.worked_seconds += seconds

        self.punch_blocks.append(f"{self.entry_time.strftime('%H:%M')} - {time_str}")
        self.entry_time = None


class TimeCalculationService:
    def calculate_daily_time(
            self,
            day_records: list[TimeRecord],
            expected_seconds: float,
            waiver_adj: AdjustmentRequest | None = None,
            unapproved_extra_adjs: list[AdjustmentRequest] | None = None,
            is_excused: bool = False,
            has_schedule: bool = True
    ) -> DailyTimeResult:

        raw_worked_seconds, entries, exits, punches, blocks = self._process_records(day_records)

        waiver_seconds = self._calculate_waiver(
            waiver_adj, is_excused
        )

        adjusted_worked_seconds = raw_worked_seconds + waiver_seconds

        unapproved_extra_seconds = self._calculate_unapproved_extra(
            unapproved_extra_adjs or [], adjusted_worked_seconds
        )

        net_worked_seconds = adjusted_worked_seconds - unapproved_extra_seconds

        gross_worked_seconds = net_worked_seconds + unapproved_extra_seconds

        extra_seconds = 0.0
        missing_seconds = 0.0

        if has_schedule:
            balance = net_worked_seconds - expected_seconds
            extra_seconds = balance if balance > 0 else 0.0
            missing_seconds = abs(balance) if balance < 0 else 0.0

        return DailyTimeResult(
            raw_worked_seconds=gross_worked_seconds,
            waiver_seconds=waiver_seconds,
            unapproved_extra_seconds=unapproved_extra_seconds,
            net_worked_seconds=net_worked_seconds,
            gross_worked_seconds=gross_worked_seconds,
            extra_seconds=extra_seconds,
            missing_seconds=missing_seconds,
            entries=entries,
            exits=exits,
            punches=punches,
            punch_blocks=blocks
        )

    def _process_records(self, day_records: list[TimeRecord]):
        state = _DailyProcessState()

        for rec in day_records:
            state.handle_record(rec)

        if state.entry_time is not None:
            state.punch_blocks.append(f"{state.entry_time.strftime('%H:%M')} - --:--")

        return state.worked_seconds, state.entries, state.exits, state.punches, state.punch_blocks

    def _calculate_waiver(
            self,
            waiver_adj: AdjustmentRequest | None,
            is_excused: bool
    ) -> float:
        if not (is_excused or waiver_adj):
            return 0.0

        if waiver_adj and waiver_adj.amount_hours and waiver_adj.amount_hours > 0:
            return waiver_adj.amount_hours * 3600

        return 0.0

    def _calculate_unapproved_extra(
            self,
            unapproved_extra_adjs: list[AdjustmentRequest],
            worked_seconds: float
    ) -> float:
        unapproved_extra_seconds = 0.0

        for adj in unapproved_extra_adjs:
            if not adj.amount_hours:
                continue
            if adj.amount_hours > 24:
                unapproved_extra_seconds += (adj.amount_hours / 60.0) * 3600
            else:
                unapproved_extra_seconds += adj.amount_hours * 3600

        if unapproved_extra_seconds > worked_seconds:
            return worked_seconds

        return unapproved_extra_seconds

    def calculate_period_time(
            self,
            start_date: date,
            end_date: date,
            records: list[TimeRecord],
            adjustments: list[AdjustmentRequest],
            holidays: list,
            historical_schedules: list
    ) -> PeriodTimeResult:

        has_schedule = bool(historical_schedules)
        total_net = 0.0
        total_gross = 0.0
        total_expected = 0.0
        total_waiver = 0.0
        total_unapproved = 0.0
        total_extra = 0.0
        total_missing = 0.0

        daily_results = {}
        daily_expected = {}
        daily_is_holiday = {}
        daily_waivers = {}

        current_date = start_date
        while current_date <= end_date:
            day_records = [r for r in records if r.record_datetime.date() == current_date]
            day_records.sort(key=lambda x: x.record_datetime)

            is_holiday = any(h.date == current_date for h in holidays)
            daily_is_holiday[current_date] = is_holiday

            day_expected_hours = 0.0
            if not is_holiday and has_schedule:
                target_day = DayOfWeek.from_date(current_date)
                valid_schedules = [
                    s for s in historical_schedules
                    if s.valid_from <= current_date and (s.valid_until is None or s.valid_until >= current_date)
                ]
                schedule = next((s for s in valid_schedules if s.day_of_week == target_day.value), None)
                if schedule:
                    day_expected_hours = schedule.daily_hours

            daily_expected[current_date] = day_expected_hours * 3600
            total_expected += day_expected_hours * 3600

            abono = next((adj for adj in adjustments if
                          adj.target_date == current_date and
                          adj.adjustment_type == AdjustmentType.WAIVER and
                          adj.status == AdjustmentStatus.APPROVED), None)

            daily_waivers[current_date] = abono

            day_unapproved_extras = [adj for adj in adjustments if
                                     adj.target_date == current_date and
                                     adj.adjustment_type == AdjustmentType.EXTRA_TIME and
                                     adj.status in [AdjustmentStatus.PENDING, AdjustmentStatus.REJECTED]]

            daily_result = self.calculate_daily_time(
                day_records=day_records,
                expected_seconds=day_expected_hours * 3600,
                waiver_adj=abono,
                unapproved_extra_adjs=day_unapproved_extras,
                is_excused=bool(abono),
                has_schedule=has_schedule
            )

            daily_results[current_date] = daily_result

            total_net += daily_result.net_worked_seconds
            total_gross += daily_result.gross_worked_seconds
            total_waiver += daily_result.waiver_seconds
            total_unapproved += daily_result.unapproved_extra_seconds
            total_extra += daily_result.extra_seconds
            total_missing += daily_result.missing_seconds

            current_date += timedelta(days=1)

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
            daily_waivers=daily_waivers
        )


time_calculation_service = TimeCalculationService()
