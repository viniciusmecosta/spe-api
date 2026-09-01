from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import User, UserWorkScheduleConfig
from app.shared.daily_excess_cron_service import DailyExcessCronService
from app.shared.enums import AdjustmentStatus, AdjustmentType, DayOfWeek, RecordType
from app.shared.time_calculation_service import DailyAccountedResult


@pytest.fixture
def cron_service():
    return DailyExcessCronService()


def test_process_daily_excess_sync_no_unverified(cron_service):
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = []
    with patch("app.shared.daily_excess_cron_service.get_db_session") as mock_get_db:
        mock_get_db.return_value.__enter__.return_value = mock_db
        cron_service.process_daily_excess()
    mock_db.commit.assert_called_once()


def test_process_daily_excess_sync_with_excess(cron_service):
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

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.side_effect = [
        [r1, r2],
        [],
    ]
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [r1, r2]
    mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = schedule

    with patch("app.shared.daily_excess_cron_service.get_db_session") as mock_get_db:
        mock_get_db.return_value.__enter__.return_value = mock_db
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
            cron_service.process_daily_excess()

    mock_db.add.assert_called_once()
    added = mock_db.add.call_args[0][0]
    assert isinstance(added, AdjustmentRequest)
    assert added.adjustment_type == AdjustmentType.DAILY_EXCESS
    assert added.status == AdjustmentStatus.PENDING
    assert added.amount_hours == 2.0
    assert r1.is_verified is True
    assert r2.is_verified is True
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_process_daily_excess_async_with_excess(cron_service):
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

    mock_scalars_pairs = MagicMock()
    mock_scalars_pairs.all.return_value = [r1, r2]

    mock_scalars_recs = MagicMock()
    mock_scalars_recs.all.return_value = [r1, r2]

    mock_scalars_adjs = MagicMock()
    mock_scalars_adjs.all.return_value = []

    db_mock.scalars.side_effect = [
        mock_scalars_pairs,
        mock_scalars_recs,
        mock_scalars_adjs,
    ]
    db_mock.scalar.return_value = schedule

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
        await cron_service.async_process_daily_excess(db=db_mock)

    db_mock.add.assert_called_once()
    added_adj = db_mock.add.call_args[0][0]
    assert isinstance(added_adj, AdjustmentRequest)
    assert added_adj.adjustment_type == AdjustmentType.DAILY_EXCESS
    assert added_adj.status == AdjustmentStatus.PENDING
    assert added_adj.amount_hours == 2.0
    assert r1.is_verified is True
    assert r2.is_verified is True
    db_mock.commit.assert_called_once()


@pytest.mark.asyncio
async def test_process_daily_excess_async_no_excess(cron_service):
    tz = ZoneInfo("America/Sao_Paulo")
    dt1 = datetime(2026, 8, 1, 8, 0, tzinfo=tz)
    dt2 = datetime(2026, 8, 1, 16, 0, tzinfo=tz)
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

    mock_scalars_pairs = MagicMock()
    mock_scalars_pairs.all.return_value = [r1, r2]
    mock_scalars_recs = MagicMock()
    mock_scalars_recs.all.return_value = [r1, r2]
    mock_scalars_adjs = MagicMock()
    mock_scalars_adjs.all.return_value = []

    db_mock.scalars.side_effect = [
        mock_scalars_pairs,
        mock_scalars_recs,
        mock_scalars_adjs,
    ]
    db_mock.scalar.return_value = schedule

    with patch("app.shared.time_calculation_service.time_calculation_service.calculate_accounted_time") as mock_calc:
        mock_calc.return_value = DailyAccountedResult(
            raw_seconds=28800.0,
            excess_work_seconds=0.0,
            excess_lunch_seconds=0.0,
            early_return_seconds=0.0,
            total_excess_seconds=0.0,
            approved_seconds=0.0,
            accounted_seconds=28800.0,
            has_schedule=True,
            has_lunch_rule=False,
        )
        await cron_service.async_process_daily_excess(db=db_mock)

    db_mock.add.assert_not_called()
    assert r1.is_verified is True
    assert r2.is_verified is True
    db_mock.commit.assert_called_once()


def test_process_daily_excess_sync_with_lunch_and_work_excess(cron_service):
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
    mock_db.query.return_value.filter.return_value.all.side_effect = [
        [r1, r2],
        [old_adj],
    ]
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [r1, r2]
    mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = schedule

    with patch("app.shared.daily_excess_cron_service.get_db_session") as mock_get_db:
        mock_get_db.return_value.__enter__.return_value = mock_db
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
            cron_service.process_daily_excess()

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


def test_process_daily_excess_sync_no_schedule(cron_service):
    tz = ZoneInfo("America/Sao_Paulo")
    dt1 = datetime(2026, 8, 1, 8, 0, tzinfo=tz)
    r1 = TimeRecord(id=1, user_id=10, record_datetime=dt1, record_type=RecordType.ENTRY, is_verified=False)

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.side_effect = [
        [r1],
        [],
    ]
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [r1]
    mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

    with patch("app.shared.daily_excess_cron_service.get_db_session") as mock_get_db:
        mock_get_db.return_value.__enter__.return_value = mock_db
        cron_service.process_daily_excess()

    mock_db.add.assert_not_called()
    assert r1.is_verified is True


def test_process_daily_excess_sync_errors_handled(cron_service):
    from sqlalchemy.exc import SQLAlchemyError
    with patch("app.shared.daily_excess_cron_service.get_db_session", side_effect=SQLAlchemyError("DB down")):
        cron_service.process_daily_excess()

    with patch("app.shared.daily_excess_cron_service.get_db_session", side_effect=RuntimeError("Unexpected")):
        cron_service.process_daily_excess()


@pytest.mark.asyncio
async def test_async_process_daily_excess_empty_and_error(cron_service):
    db_mock = AsyncMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    db_mock.scalars.return_value = mock_scalars

    await cron_service.async_process_daily_excess(db=db_mock)
    db_mock.commit.assert_not_called()

    r1 = TimeRecord(id=1, user_id=10, record_datetime=datetime(2026, 8, 1, 8, 0), record_type=RecordType.ENTRY, is_verified=False)
    mock_scalars.all.return_value = [r1]
    with patch.object(cron_service, "_evaluate_user_day_async", side_effect=Exception("User eval failed")):
        await cron_service.async_process_daily_excess(db=db_mock)
    db_mock.commit.assert_called_once()


def test_evaluate_user_day_sync_public(cron_service):
    mock_db = MagicMock()
    with patch.object(cron_service, "_evaluate_user_day_sync") as mock_eval:
        cron_service.evaluate_user_day_sync(mock_db, 10, date(2026, 8, 1))
        mock_eval.assert_called_once()


@pytest.mark.asyncio
async def test_evaluate_user_day_async_public(cron_service):
    db_mock = AsyncMock()
    with patch.object(cron_service, "_evaluate_user_day_async") as mock_eval:
        await cron_service.evaluate_user_day_async(db_mock, 10, date(2026, 8, 1))
        mock_eval.assert_called_once()

