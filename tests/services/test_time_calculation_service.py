from datetime import date, datetime
from unittest.mock import MagicMock

import pytest

from app.domain.models.adjustment import AdjustmentRequest
from app.domain.models.enums import AdjustmentStatus, AdjustmentType, RecordType
from app.domain.models.time_record import TimeRecord
from app.services.time_calculation_service import (
    TimeCalculationService,
    _DailyProcessState,
    time_calculation_service,
)

def test_daily_process_state_handle_record_entry_exit():
    state = _DailyProcessState()
    
    rec_entry = MagicMock(spec=TimeRecord)
    rec_entry.record_type = RecordType.ENTRY
    rec_entry.record_datetime = datetime(2024, 1, 1, 8, 0, 0)
    
    rec_exit = MagicMock(spec=TimeRecord)
    rec_exit.record_type = RecordType.EXIT
    rec_exit.record_datetime = datetime(2024, 1, 1, 12, 0, 0)
    
    state.handle_record(rec_entry)
    assert state.entries == ["08:00"]
    assert state.punches == ["08:00 (E)"]
    assert state.entry_time == datetime(2024, 1, 1, 8, 0, 0)
    
    state.handle_record(rec_exit)
    assert state.exits == ["12:00"]
    assert state.punches == ["08:00 (E)", "12:00 (S)"]
    assert state.punch_blocks == ["08:00 - 12:00"]
    assert state.worked_seconds == 14400.0

def test_daily_process_state_multiple_entries():
    state = _DailyProcessState()
    
    rec_entry1 = MagicMock(spec=TimeRecord)
    rec_entry1.record_type = RecordType.ENTRY
    rec_entry1.record_datetime = datetime(2024, 1, 1, 8, 0, 0)
    
    rec_entry2 = MagicMock(spec=TimeRecord)
    rec_entry2.record_type = RecordType.ENTRY
    rec_entry2.record_datetime = datetime(2024, 1, 1, 10, 0, 0)
    
    state.handle_record(rec_entry1)
    state.handle_record(rec_entry2)
    
    assert state.punch_blocks == ["08:00 - --:--"]
    assert state.entry_time == datetime(2024, 1, 1, 10, 0, 0)

def test_daily_process_state_exit_without_entry():
    state = _DailyProcessState()
    
    rec_exit = MagicMock(spec=TimeRecord)
    rec_exit.record_type = RecordType.EXIT
    rec_exit.record_datetime = datetime(2024, 1, 1, 12, 0, 0)
    
    state.handle_record(rec_exit)
    assert state.punch_blocks == ["--:-- - 12:00"]
    assert state.worked_seconds == 0.0

def test_daily_process_state_exit_more_than_24_hours():
    state = _DailyProcessState()
    
    rec_entry = MagicMock(spec=TimeRecord)
    rec_entry.record_type = RecordType.ENTRY
    rec_entry.record_datetime = datetime(2024, 1, 1, 8, 0, 0)
    
    rec_exit = MagicMock(spec=TimeRecord)
    rec_exit.record_type = RecordType.EXIT
    rec_exit.record_datetime = datetime(2024, 1, 2, 9, 0, 0)
    
    state.handle_record(rec_entry)
    state.handle_record(rec_exit)
    
    assert state.worked_seconds == 0.0

def test_calculate_waiver_not_excused():
    service = TimeCalculationService()
    result = service._calculate_waiver(
        waiver_adj=None,
        is_excused=False,
        expected_seconds=28800.0,
        worked_seconds=14400.0
    )
    assert result == 0.0

def test_calculate_waiver_with_amount_hours():
    service = TimeCalculationService()
    waiver = MagicMock(spec=AdjustmentRequest)
    waiver.amount_hours = 2.0
    
    result = service._calculate_waiver(
        waiver_adj=waiver,
        is_excused=True,
        expected_seconds=28800.0,
        worked_seconds=14400.0
    )
    assert result == 7200.0

def test_calculate_waiver_less_than_expected():
    service = TimeCalculationService()
    waiver = MagicMock(spec=AdjustmentRequest)
    waiver.amount_hours = None
    
    result = service._calculate_waiver(
        waiver_adj=waiver,
        is_excused=True,
        expected_seconds=28800.0,
        worked_seconds=14400.0
    )
    assert result == 0.0

def test_calculate_waiver_more_than_expected():
    service = TimeCalculationService()
    waiver = MagicMock(spec=AdjustmentRequest)
    waiver.amount_hours = None
    
    result = service._calculate_waiver(
        waiver_adj=waiver,
        is_excused=True,
        expected_seconds=28800.0,
        worked_seconds=30000.0
    )
    assert result == 0.0

def test_calculate_waiver_excused_no_waiver_adj():
    service = TimeCalculationService()
    result = service._calculate_waiver(
        waiver_adj=None,
        is_excused=True,
        expected_seconds=28800.0,
        worked_seconds=14400.0
    )
    assert result == 0.0

def test_calculate_unapproved_extra():
    service = TimeCalculationService()
    
    adj1 = MagicMock(spec=AdjustmentRequest)
    adj1.amount_hours = None
    
    adj2 = MagicMock(spec=AdjustmentRequest)
    adj2.amount_hours = 2.0
    
    adj3 = MagicMock(spec=AdjustmentRequest)
    adj3.amount_hours = 30.0
    
    result = service._calculate_unapproved_extra(
        unapproved_extra_adjs=[adj1, adj2, adj3],
        worked_seconds=28800.0
    )
    assert result == 9000.0

def test_calculate_unapproved_extra_caps_at_worked():
    service = TimeCalculationService()
    
    adj1 = MagicMock(spec=AdjustmentRequest)
    adj1.amount_hours = 4.0
    
    result = service._calculate_unapproved_extra(
        unapproved_extra_adjs=[adj1],
        worked_seconds=7200.0
    )
    assert result == 7200.0

def test_process_records_missing_exit():
    service = TimeCalculationService()
    
    rec_entry = MagicMock(spec=TimeRecord)
    rec_entry.record_type = RecordType.ENTRY
    rec_entry.record_datetime = datetime(2024, 1, 1, 8, 0, 0)
    
    worked, entries, exits, punches, blocks = service._process_records([rec_entry])
    assert worked == 0.0
    assert entries == ["08:00"]
    assert exits == []
    assert punches == ["08:00 (E)"]
    assert blocks == ["08:00 - --:--"]

def test_calculate_daily_time(db_session_mock):
    service = time_calculation_service
    
    rec_entry = MagicMock(spec=TimeRecord)
    rec_entry.record_type = RecordType.ENTRY
    rec_entry.record_datetime = datetime(2024, 1, 1, 8, 0, 0)
    
    rec_exit = MagicMock(spec=TimeRecord)
    rec_exit.record_type = RecordType.EXIT
    rec_exit.record_datetime = datetime(2024, 1, 1, 12, 0, 0)
    
    waiver_adj = MagicMock(spec=AdjustmentRequest)
    waiver_adj.amount_hours = 1.0
    
    unapproved_adj = MagicMock(spec=AdjustmentRequest)
    unapproved_adj.amount_hours = 0.5
    
    result = service.calculate_daily_time(
        day_records=[rec_entry, rec_exit],
        expected_seconds=28800.0,
        waiver_adj=waiver_adj,
        unapproved_extra_adjs=[unapproved_adj],
        is_excused=True
    )
    
    assert result.raw_worked_seconds == 18000.0
    assert result.waiver_seconds == 3600.0
    assert result.unapproved_extra_seconds == 1800.0
    assert result.net_worked_seconds == 16200.0
    assert result.gross_worked_seconds == 18000.0
    assert result.entries == ["08:00"]
    assert result.exits == ["12:00"]
    assert result.punches == ["08:00 (E)", "12:00 (S)"]
    assert result.punch_blocks == ["08:00 - 12:00"]

def test_calculate_period_time(db_session_mock):
    service = time_calculation_service
    
    start_date = date(2024, 1, 1)
    end_date = date(2024, 1, 2)
    
    rec_entry = MagicMock(spec=TimeRecord)
    rec_entry.record_type = RecordType.ENTRY
    rec_entry.record_datetime = datetime(2024, 1, 1, 8, 0, 0)
    
    rec_exit = MagicMock(spec=TimeRecord)
    rec_exit.record_type = RecordType.EXIT
    rec_exit.record_datetime = datetime(2024, 1, 1, 16, 0, 0)
    
    holiday = MagicMock()
    holiday.date = date(2024, 1, 2)
    
    schedule_1 = MagicMock()
    schedule_1.valid_from = date(2024, 1, 1)
    schedule_1.valid_until = None
    schedule_1.day_of_week = 0
    schedule_1.daily_hours = 8.0
    
    waiver_adj = MagicMock(spec=AdjustmentRequest)
    waiver_adj.target_date = date(2024, 1, 1)
    waiver_adj.adjustment_type = AdjustmentType.WAIVER
    waiver_adj.status = AdjustmentStatus.APPROVED
    waiver_adj.amount_hours = 0.0
    
    extra_adj = MagicMock(spec=AdjustmentRequest)
    extra_adj.target_date = date(2024, 1, 1)
    extra_adj.adjustment_type = AdjustmentType.EXTRA_TIME
    extra_adj.status = AdjustmentStatus.PENDING
    extra_adj.amount_hours = 1.0
    
    result = service.calculate_period_time(
        start_date=start_date,
        end_date=end_date,
        records=[rec_entry, rec_exit],
        adjustments=[waiver_adj, extra_adj],
        holidays=[holiday],
        historical_schedules=[schedule_1]
    )
    
    assert result.total_expected_seconds == 28800.0
    assert result.total_net_worked_seconds == 25200.0
    assert result.total_gross_worked_seconds == 28800.0
    assert result.total_waiver_seconds == 0.0
    assert result.total_unapproved_extra_seconds == 3600.0
    
    assert result.daily_expected_seconds[date(2024, 1, 1)] == 28800.0
    assert result.daily_expected_seconds[date(2024, 1, 2)] == 0.0
    
    assert result.daily_is_holiday[date(2024, 1, 1)] is False
    assert result.daily_is_holiday[date(2024, 1, 2)] is True
    
    assert result.daily_waivers[date(2024, 1, 1)] == waiver_adj
    assert result.daily_waivers[date(2024, 1, 2)] is None

def test_calculate_period_time_schedule_validity(db_session_mock):
    service = time_calculation_service
    
    start_date = date(2024, 1, 1)
    end_date = date(2024, 1, 1)
    
    schedule_expired = MagicMock()
    schedule_expired.valid_from = date(2023, 1, 1)
    schedule_expired.valid_until = date(2023, 12, 31)
    schedule_expired.day_of_week = 0
    schedule_expired.daily_hours = 8.0
    
    schedule_future = MagicMock()
    schedule_future.valid_from = date(2024, 1, 2)
    schedule_future.valid_until = None
    schedule_future.day_of_week = 0
    schedule_future.daily_hours = 8.0
    
    result = service.calculate_period_time(
        start_date=start_date,
        end_date=end_date,
        records=[],
        adjustments=[],
        holidays=[],
        historical_schedules=[schedule_expired, schedule_future]
    )
    
    assert result.total_expected_seconds == 0.0
