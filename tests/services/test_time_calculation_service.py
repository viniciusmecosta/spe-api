import pytest
from datetime import date, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

from app.domain.models.enums import RecordType, AdjustmentType, AdjustmentStatus, DayOfWeek
from app.domain.models.time_record import TimeRecord
from app.domain.models.adjustment import AdjustmentRequest
from app.services.time_calculation_service import time_calculation_service, _DailyProcessState, PeriodTimeResult, DailyTimeResult

@pytest.fixture
def record_factory():
    def _factory(dt: datetime, record_type: RecordType) -> TimeRecord:
        rec = MagicMock(spec=TimeRecord)
        rec.record_datetime = dt
        rec.record_type = record_type
        return rec
    return _factory

@pytest.fixture
def adjustment_factory():
    def _factory(target_date: date, adj_type: AdjustmentType, status: AdjustmentStatus, hours: float | None) -> AdjustmentRequest:
        adj = MagicMock(spec=AdjustmentRequest)
        adj.target_date = target_date
        adj.adjustment_type = adj_type
        adj.status = status
        adj.amount_hours = hours
        return adj
    return _factory

@pytest.fixture
def schedule_factory():
    def _factory(valid_from: date, valid_until: date | None, day: int, hours: float) -> Any:
        sched = MagicMock()
        sched.valid_from = valid_from
        sched.valid_until = valid_until
        sched.day_of_week = day
        sched.daily_hours = hours
        return sched
    return _factory

@pytest.mark.parametrize(
    "punch_times, expected_worked, expected_blocks, expected_punches",
    [
        (
            [("08:00", RecordType.ENTRY), ("12:00", RecordType.EXIT)],
            14400.0,
            ["08:00 - 12:00"],
            ["08:00 (E)", "12:00 (S)"]
        ),
        (
            [("08:00", RecordType.ENTRY), ("12:00", RecordType.EXIT), ("13:00", RecordType.ENTRY), ("18:00", RecordType.EXIT)],
            32400.0,
            ["08:00 - 12:00", "13:00 - 18:00"],
            ["08:00 (E)", "12:00 (S)", "13:00 (E)", "18:00 (S)"]
        ),
        (
            [("08:00", RecordType.ENTRY)],
            0.0,
            ["08:00 - --:--"],
            ["08:00 (E)"]
        ),
        (
            [("18:00", RecordType.EXIT)],
            0.0,
            ["--:-- - 18:00"],
            ["18:00 (S)"]
        ),
        (
            [("08:00", RecordType.ENTRY), ("09:00", RecordType.ENTRY), ("12:00", RecordType.EXIT)],
            10800.0,
            ["08:00 - --:--", "09:00 - 12:00"],
            ["08:00 (E)", "09:00 (E)", "12:00 (S)"]
        ),
        (
            [("08:00", RecordType.ENTRY), ("10:00", RecordType.EXIT), ("12:00", RecordType.EXIT)],
            7200.0,
            ["08:00 - 10:00", "--:-- - 12:00"],
            ["08:00 (E)", "10:00 (S)", "12:00 (S)"]
        ),
        (
            [],
            0.0,
            [],
            []
        )
    ]
)
def test_process_records_matrix(record_factory, punch_times, expected_worked, expected_blocks, expected_punches):
    records = []
    for time_str, r_type in punch_times:
        hr, mn = map(int, time_str.split(":"))
        dt = datetime(2023, 10, 10, hr, mn, 0)
        records.append(record_factory(dt, r_type))
        
    worked, entries, exits, punches, blocks = time_calculation_service._process_records(records)
    
    assert worked == expected_worked
    assert blocks == expected_blocks
    assert punches == expected_punches

def test_daily_process_state_over_24h(record_factory):
    state = _DailyProcessState()
    r1 = record_factory(datetime(2023, 10, 10, 8, 0, 0), RecordType.ENTRY)
    r2 = record_factory(datetime(2023, 10, 11, 9, 0, 0), RecordType.EXIT)
    state.handle_record(r1)
    state.handle_record(r2)
    assert state.worked_seconds == 0.0

@pytest.mark.parametrize(
    "is_excused, adj_hours, expected_waiver_sec",
    [
        (False, None, 0.0),
        (True, None, 0.0),
        (True, 0.0, 0.0),
        (True, 2.0, 7200.0),
        (True, 8.0, 28800.0),
        (False, 2.0, 7200.0)
    ]
)
def test_calculate_waiver_matrix(adjustment_factory, is_excused, adj_hours, expected_waiver_sec):
    adj = adjustment_factory(date(2023,10,10), AdjustmentType.WAIVER, AdjustmentStatus.APPROVED, adj_hours) if adj_hours is not None else None
    assert time_calculation_service._calculate_waiver(adj, is_excused, 28800, 0) == expected_waiver_sec

@pytest.mark.parametrize(
    "adj_hours_list, worked_seconds, expected_unapproved_sec",
    [
        ([None], 10000.0, 0.0),
        ([0.0], 10000.0, 0.0),
        ([1.0], 10000.0, 3600.0),
        ([1.5], 10000.0, 5400.0),
        ([1.0, 2.0], 20000.0, 10800.0),
        ([10.0], 3600.0, 3600.0),
        ([90.0], 10000.0, 5400.0),
        ([60.0, 1.0], 10000.0, 7200.0),
        ([], 10000.0, 0.0)
    ]
)
def test_calculate_unapproved_extra_matrix(adjustment_factory, adj_hours_list, worked_seconds, expected_unapproved_sec):
    adjs = [
        adjustment_factory(date(2023,10,10), AdjustmentType.EXTRA_TIME, AdjustmentStatus.REJECTED, hr)
        for hr in adj_hours_list
    ]
    assert time_calculation_service._calculate_unapproved_extra(adjs, worked_seconds) == expected_unapproved_sec

@pytest.mark.parametrize(
    "raw_worked, expected_sec, waiver_hr, unapproved_hr, has_schedule, exp_net, exp_gross, exp_extra, exp_missing",
    [
        (28800.0, 28800.0, 0.0, 0.0, True, 28800.0, 28800.0, 0.0, 0.0),
        (36000.0, 28800.0, 0.0, 0.0, True, 36000.0, 36000.0, 7200.0, 0.0),
        (36000.0, 28800.0, 0.0, 2.0, True, 28800.0, 36000.0, 0.0, 0.0),
        (18000.0, 28800.0, 3.0, 0.0, True, 28800.0, 28800.0, 0.0, 0.0),
        (18000.0, 28800.0, 0.0, 0.0, True, 18000.0, 18000.0, 0.0, 10800.0),
        (18000.0, 28800.0, 5.0, 0.0, True, 36000.0, 36000.0, 7200.0, 0.0),
        (0.0, 28800.0, 0.0, 0.0, True, 0.0, 0.0, 0.0, 28800.0),
        (0.0, 28800.0, 8.0, 0.0, True, 28800.0, 28800.0, 0.0, 0.0),
        (36000.0, 0.0, 0.0, 0.0, False, 36000.0, 36000.0, 0.0, 0.0),
        (36000.0, 28800.0, 0.0, 10.0, True, 0.0, 36000.0, 0.0, 28800.0)
    ]
)
def test_calculate_daily_time_matrix(record_factory, adjustment_factory, monkeypatch, 
                                     raw_worked, expected_sec, waiver_hr, unapproved_hr, has_schedule,
                                     exp_net, exp_gross, exp_extra, exp_missing):
    monkeypatch.setattr(time_calculation_service, "_process_records", lambda recs: (raw_worked, [], [], [], []))
    
    waiver = adjustment_factory(date(2023,10,10), AdjustmentType.WAIVER, AdjustmentStatus.APPROVED, waiver_hr) if waiver_hr else None
    unapproved = adjustment_factory(date(2023,10,10), AdjustmentType.EXTRA_TIME, AdjustmentStatus.PENDING, unapproved_hr) if unapproved_hr else None
    
    res = time_calculation_service.calculate_daily_time(
        day_records=[],
        expected_seconds=expected_sec,
        waiver_adj=waiver,
        unapproved_extra_adjs=[unapproved] if unapproved else [],
        is_excused=bool(waiver),
        has_schedule=has_schedule
    )
    
    assert res.net_worked_seconds == exp_net
    assert res.gross_worked_seconds == exp_gross
    assert res.extra_seconds == exp_extra
    assert res.missing_seconds == exp_missing

@pytest.mark.parametrize(
    "scenario_name, start, end, schedules, holidays, expected_total_net, expected_total_missing, expected_total_extra",
    [
        (
            "standard_week",
            date(2023, 10, 9),
            date(2023, 10, 13),
            [(DayOfWeek.SEGUNDA.value, 8.0), (DayOfWeek.TERCA.value, 8.0), (DayOfWeek.QUARTA.value, 8.0), (DayOfWeek.QUINTA.value, 8.0), (DayOfWeek.SEXTA.value, 8.0)],
            [],
            144000.0,
            0.0,
            0.0
        ),
        (
            "holiday_mid_week",
            date(2023, 10, 9),
            date(2023, 10, 13),
            [(DayOfWeek.SEGUNDA.value, 8.0), (DayOfWeek.TERCA.value, 8.0), (DayOfWeek.QUARTA.value, 8.0), (DayOfWeek.QUINTA.value, 8.0), (DayOfWeek.SEXTA.value, 8.0)],
            [date(2023, 10, 11)],
            115200.0,
            0.0,
            0.0
        ),
        (
            "no_schedule",
            date(2023, 10, 9),
            date(2023, 10, 13),
            [],
            [],
            0.0,
            0.0,
            0.0
        )
    ]
)
def test_calculate_period_time_schedules_matrix(record_factory, schedule_factory, monkeypatch, 
                                                scenario_name, start, end, schedules, holidays, 
                                                expected_total_net, expected_total_missing, expected_total_extra):
    hist_sched = []
    for day, hr in schedules:
        hist_sched.append(schedule_factory(date(2023, 1, 1), None, day, hr))
        
    hol_mocks = []
    for h in holidays:
        hm = MagicMock()
        hm.date = h
        hol_mocks.append(hm)

    def mock_daily_time(day_records, expected_seconds, waiver_adj, unapproved_extra_adjs, is_excused, has_schedule):
        dt = DailyTimeResult(
            raw_worked_seconds=expected_seconds,
            waiver_seconds=0.0,
            unapproved_extra_seconds=0.0,
            net_worked_seconds=expected_seconds,
            gross_worked_seconds=expected_seconds,
            extra_seconds=0.0,
            missing_seconds=0.0,
            entries=[], exits=[], punches=[], punch_blocks=[]
        )
        return dt
        
    monkeypatch.setattr(time_calculation_service, "calculate_daily_time", mock_daily_time)
    
    res = time_calculation_service.calculate_period_time(
        start_date=start,
        end_date=end,
        records=[],
        adjustments=[],
        holidays=hol_mocks,
        historical_schedules=hist_sched
    )
    
    assert res.total_net_worked_seconds == expected_total_net
    assert res.total_missing_seconds == expected_total_missing
    assert res.total_extra_seconds == expected_total_extra

def test_calculate_period_time_pure_logic(record_factory, schedule_factory, adjustment_factory):
    r1 = record_factory(datetime(2023, 10, 10, 8, 0, 0), RecordType.ENTRY)
    r2 = record_factory(datetime(2023, 10, 10, 18, 0, 0), RecordType.EXIT)
    
    sched = schedule_factory(date(2023, 1, 1), None, DayOfWeek.TERCA.value, 8.0)
    
    res = time_calculation_service.calculate_period_time(
        start_date=date(2023, 10, 10),
        end_date=date(2023, 10, 10),
        records=[r1, r2],
        adjustments=[],
        holidays=[],
        historical_schedules=[sched]
    )
    
    assert res.total_expected_seconds == 28800.0
    assert res.total_net_worked_seconds == 36000.0
    assert res.total_extra_seconds == 7200.0
    assert res.total_missing_seconds == 0.0
    assert res.final_balance_seconds == 7200.0
