from datetime import date, datetime, time
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import UserWorkScheduleConfig
from app.shared.daily_excess_service import DailyExcessService
from app.shared.enums import AdjustmentStatus, AdjustmentType, DayOfWeek, RecordType
from app.shared.time_calculation_service import DailyAccountedResult


@pytest.fixture
def excess_service():
    return DailyExcessService()


@pytest.mark.asyncio
async def test_evaluate_user_day_async_with_excess(excess_service):
    tz = ZoneInfo("America/Sao_Paulo")
    dt1 = datetime(2026, 8, 1, 8, 0, tzinfo=tz)
    dt2 = datetime(2026, 8, 1, 18, 0, tzinfo=tz)
    r1 = TimeRecord(id=1, user_id=10, record_datetime=dt1, record_type=RecordType.ENTRY, is_verified=False)
    r2 = TimeRecord(id=2, user_id=10, record_datetime=dt2, record_type=RecordType.EXIT, is_verified=False)

    schedule = UserWorkScheduleConfig(
        id=1,
        user_id=10,
        day_of_week=DayOfWeek.SABADO.value,
        daily_hours=8.0,
        valid_from=date(2026, 1, 1),
        valid_until=None,
    )

    db_mock = AsyncMock()
    db_mock.sync_session = MagicMock()
    db_mock.add = MagicMock()

    mock_scalars_recs = MagicMock()
    mock_scalars_recs.all.return_value = [r1, r2]

    mock_scalars_adjs = MagicMock()
    mock_scalars_adjs.all.return_value = []

    db_mock.scalars.side_effect = [
        mock_scalars_recs,
        mock_scalars_adjs,
    ]
    db_mock.scalar.side_effect = [None, None, schedule]

    with patch("app.shared.time_calculation_service.time_calculation_service.calculate_accounted_time") as mock_calc:
        mock_calc.return_value = DailyAccountedResult(
            raw_seconds=36000.0,
            excess_work_seconds=7200.0,
            excess_lunch_seconds=0.0,
            early_return_seconds=0.0,
            total_excess_seconds=7200.0,
            approved_seconds=0.0,
            accounted_seconds=28800.0,
            has_schedule=True,
            has_lunch_rule=False,
        )
        await excess_service.evaluate_user_day_async(db_mock, 10, date(2026, 8, 1))

    db_mock.add.assert_called_once()
    added_adj = db_mock.add.call_args[0][0]
    assert isinstance(added_adj, AdjustmentRequest)
    assert added_adj.adjustment_type == AdjustmentType.DAILY_EXCESS
    assert added_adj.status == AdjustmentStatus.PENDING
    assert added_adj.amount_hours == 2.0
    assert r1.is_verified is True
    assert r2.is_verified is True


def test_evaluate_user_day_sync_with_lunch_and_work_excess(excess_service):
    tz = ZoneInfo("America/Sao_Paulo")
    dt1 = datetime(2026, 8, 1, 8, 0, tzinfo=tz)
    dt2 = datetime(2026, 8, 1, 19, 0, tzinfo=tz)
    r1 = TimeRecord(id=1, user_id=10, record_datetime=dt1, record_type=RecordType.ENTRY, is_verified=False)
    r2 = TimeRecord(id=2, user_id=10, record_datetime=dt2, record_type=RecordType.EXIT, is_verified=False)

    schedule = UserWorkScheduleConfig(
        id=1,
        user_id=10,
        day_of_week=DayOfWeek.SABADO.value,
        daily_hours=8.0,
        valid_from=date(2026, 1, 1),
        valid_until=None,
    )

    old_adj = AdjustmentRequest(
        id=99,
        user_id=10,
        adjustment_type=AdjustmentType.DAILY_EXCESS,
        target_date=date(2026, 8, 1),
        status=AdjustmentStatus.PENDING
    )

    mock_db = MagicMock()
    # We have 5 queries in sync:
    # 1. PayrollClosure.first() -> None
    # 2. AdjustmentRequest EXTRA_TIME.first() -> None
    # 3. TimeRecord.order_by.all() -> [r1, r2]
    # 4. UserWorkScheduleConfig.first() -> schedule
    # 5. AdjustmentRequest DAILY_EXCESS.all() -> [old_adj]
    
    mock_q_payroll = MagicMock()
    mock_q_payroll.filter.return_value.first.return_value = None
    
    mock_q_extratime = MagicMock()
    mock_q_extratime.filter.return_value.first.return_value = None
    
    mock_q_records = MagicMock()
    mock_q_records.filter.return_value.order_by.return_value.all.return_value = [r1, r2]
    
    mock_q_schedule = MagicMock()
    mock_q_schedule.filter.return_value.order_by.return_value.first.return_value = schedule
    mock_q_schedule.filter.return_value.first.return_value = schedule # In case order_by is missed
    
    mock_q_dailyexcess = MagicMock()
    mock_q_dailyexcess.filter.return_value.all.return_value = [old_adj]

    def query_side_effect(model):
        if model.__name__ == 'PayrollClosure':
            return mock_q_payroll
        elif model.__name__ == 'AdjustmentRequest':
            # distinguish between EXTRA_TIME and DAILY_EXCESS based on usage? 
            # Actually, both are AdjustmentRequest, so they return the same query mock.
            # We can use side_effect on the filter result.
            pass
        elif model.__name__ == 'TimeRecord':
            return mock_q_records
        elif model.__name__ == 'UserWorkScheduleConfig':
            return mock_q_schedule
        return MagicMock()
    
    mock_db.query.side_effect = query_side_effect
    
    # Since AdjustmentRequest is queried twice, let's just make its filter return a mock that handles both first() and all()
    mock_adj_filter = MagicMock()
    mock_adj_filter.first.side_effect = [None] # For EXTRA_TIME
    mock_adj_filter.all.return_value = [old_adj] # For DAILY_EXCESS
    
    mock_q_adj = MagicMock()
    mock_q_adj.filter.return_value = mock_adj_filter
    
    def query_side_effect_fixed(model):
        if model.__name__ == 'PayrollClosure': return mock_q_payroll
        if model.__name__ == 'TimeRecord': return mock_q_records
        if model.__name__ == 'UserWorkScheduleConfig': return mock_q_schedule
        if model.__name__ == 'AdjustmentRequest': return mock_q_adj
        return MagicMock()
        
    mock_db.query.side_effect = query_side_effect_fixed


    with patch("app.shared.time_calculation_service.time_calculation_service.calculate_accounted_time") as mock_calc:
        mock_calc.return_value = DailyAccountedResult(
            raw_seconds=39600.0,
            excess_work_seconds=7200.0,
            excess_lunch_seconds=1800.0,
            early_return_seconds=0.0,
            total_excess_seconds=9000.0,
            approved_seconds=0.0,
            accounted_seconds=28800.0,
            has_schedule=True,
            has_lunch_rule=True,
        )
        excess_service.evaluate_user_day_sync(mock_db, 10, date(2026, 8, 1))

    mock_db.delete.assert_called_once_with(old_adj)
    mock_db.add.assert_called_once()
    new_adj = mock_db.add.call_args[0][0]
    assert isinstance(new_adj, AdjustmentRequest)
    assert new_adj.amount_hours == 2.5
    assert "120min de jornada excedente" in new_adj.reason_text
    assert "30min de almoço excedido" in new_adj.reason_text
    assert new_adj.time == dt2.time()
    assert r1.is_verified is True
    assert r2.is_verified is True


@pytest.mark.asyncio
async def test_evaluate_user_day_bg_success(excess_service):
    db_mock = AsyncMock()
    with patch("app.shared.daily_excess_service.get_async_session_context") as mock_get_db:
        mock_get_db.return_value.__aenter__.return_value = db_mock
        with patch.object(excess_service, "_evaluate_user_day_async") as mock_eval:
            await excess_service.evaluate_user_day_bg(10, date(2026, 8, 1))
            mock_eval.assert_called_once()


@pytest.mark.asyncio
async def test_evaluate_user_day_bg_exception_handled(excess_service):
    with patch("app.shared.daily_excess_service.get_async_session_context", side_effect=Exception("DB Error")):
        await excess_service.evaluate_user_day_bg(10, date(2026, 8, 1))


@pytest.mark.asyncio
async def test_evaluate_user_range_bg(excess_service):
    db_mock = AsyncMock()
    with patch("app.shared.daily_excess_service.get_async_session_context") as mock_get_db:
        mock_get_db.return_value.__aenter__.return_value = db_mock
        with patch.object(excess_service, "_evaluate_user_day_async") as mock_eval:
            await excess_service.evaluate_user_range_bg(10, date(2026, 8, 1), date(2026, 8, 3))
            assert mock_eval.call_count == 3


@pytest.mark.asyncio
async def test_evaluate_user_range_bg_exception_handled(excess_service):
    with patch("app.shared.daily_excess_service.get_async_session_context", side_effect=Exception("Range Error")):
        await excess_service.evaluate_user_range_bg(10, date(2026, 8, 1), date(2026, 8, 3))
