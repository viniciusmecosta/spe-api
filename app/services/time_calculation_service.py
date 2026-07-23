from app.domain.models.adjustment_request import AdjustmentRequest
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict

from app.domain.models.enums import RecordType, AdjustmentType, AdjustmentStatus
from app.domain.models.time_record import TimeRecord


@dataclass
class DailyTimeResult:
    raw_worked_seconds: float
    waiver_seconds: float
    unapproved_extra_seconds: float
    net_worked_seconds: float
    gross_worked_seconds: float
    entries: List[str]
    exits: List[str]
    punches: List[str]
    punch_blocks: List[str]


@dataclass
class PeriodTimeResult:
    total_net_worked_seconds: float
    total_gross_worked_seconds: float
    total_expected_seconds: float
    total_waiver_seconds: float
    total_unapproved_extra_seconds: float
    daily_results: Dict[date, DailyTimeResult]
    daily_expected_seconds: Dict[date, float]
    daily_is_holiday: Dict[date, bool]
    daily_waivers: Dict[date, Optional[AdjustmentRequest]]


class _DailyProcessState:
    def __init__(self):
        self.entries: List[str] = []
        self.exits: List[str] = []
        self.punches: List[str] = []
        self.punch_blocks: List[str] = []
        self.worked_seconds: float = 0.0
        self.entry_time: Optional[datetime] = None

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
            day_records: List[TimeRecord],
            expected_seconds: float,
            waiver_adj: Optional[AdjustmentRequest],
            unapproved_extra_adjs: List[AdjustmentRequest],
            is_excused: bool = False
    ) -> DailyTimeResult:

        raw_worked_sec, entries, exits, punches, blocks = self._process_records(day_records)
        waiver_sec = self._calculate_waiver(waiver_adj, is_excused, expected_seconds, raw_worked_sec)
        adjusted_worked_sec = raw_worked_sec + waiver_sec
        unapproved_extra_sec = self._calculate_unapproved_extra(unapproved_extra_adjs, adjusted_worked_sec)

        net_worked_sec = adjusted_worked_sec - unapproved_extra_sec
        gross_worked_sec = net_worked_sec + unapproved_extra_sec

        return DailyTimeResult(
            raw_worked_seconds=raw_worked_sec,
            waiver_seconds=waiver_sec,
            unapproved_extra_seconds=unapproved_extra_sec,
            net_worked_seconds=net_worked_sec,
            gross_worked_seconds=gross_worked_sec,
            entries=entries,
            exits=exits,
            punches=punches,
            punch_blocks=blocks
        )

    def _process_records(self, day_records: List[TimeRecord]):
        state = _DailyProcessState()

        for rec in day_records:
            state.handle_record(rec)

        if state.entry_time is not None:
            state.punch_blocks.append(f"{state.entry_time.strftime('%H:%M')} - --:--")

        return state.worked_seconds, state.entries, state.exits, state.punches, state.punch_blocks

    def _calculate_waiver(
            self,
            waiver_adj: Optional[AdjustmentRequest],
            is_excused: bool,
            expected_seconds: float,
            worked_seconds: float
    ) -> float:
        if not (is_excused or waiver_adj):
            return 0.0

        if waiver_adj and waiver_adj.amount_hours and waiver_adj.amount_hours > 0:
            return waiver_adj.amount_hours * 3600

        if expected_seconds > 0 and worked_seconds < expected_seconds:
            return expected_seconds - worked_seconds

        return 0.0

    def _calculate_unapproved_extra(
            self,
            unapproved_extra_adjs: List[AdjustmentRequest],
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
            records: List[TimeRecord],
            adjustments: List[AdjustmentRequest],
            holidays: List,
            historical_schedules: List
    ) -> PeriodTimeResult:

        has_schedule = bool(historical_schedules)
        total_net = 0.0
        total_gross = 0.0
        total_expected = 0.0
        total_waiver = 0.0
        total_unapproved = 0.0

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
                weekday = current_date.weekday()
                valid_schedules = [
                    s for s in historical_schedules
                    if s.valid_from <= current_date and (s.valid_until is None or s.valid_until >= current_date)
                ]
                schedule = next((s for s in valid_schedules if s.day_of_week == weekday), None)
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
                is_excused=bool(abono)
            )

            daily_results[current_date] = daily_result

            total_net += daily_result.net_worked_seconds
            total_gross += daily_result.gross_worked_seconds
            total_waiver += daily_result.waiver_seconds
            total_unapproved += daily_result.unapproved_extra_seconds

            current_date += timedelta(days=1)

        return PeriodTimeResult(
            total_net_worked_seconds=total_net,
            total_gross_worked_seconds=total_gross,
            total_expected_seconds=total_expected,
            total_waiver_seconds=total_waiver,
            total_unapproved_extra_seconds=total_unapproved,
            daily_results=daily_results,
            daily_expected_seconds=daily_expected,
            daily_is_holiday=daily_is_holiday,
            daily_waivers=daily_waivers
        )


time_calculation_service = TimeCalculationService()
