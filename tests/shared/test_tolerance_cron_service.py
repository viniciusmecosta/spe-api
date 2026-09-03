from datetime import datetime, date, time
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from sqlalchemy.exc import SQLAlchemyError

import pytest
from app.shared.enums import RecordType
from app.shared.tolerance_cron_service import ToleranceCronService


def make_query_mock(items):
    qm = MagicMock()
    qm.filter.return_value = qm
    qm.order_by.return_value = qm
    qm.first.return_value = items[0] if items else None
    qm.all.return_value = items
    return qm


@pytest.fixture
def base_record():
    record = MagicMock()
    record.id = 1
    record.user_id = 1
    record.user.is_tolerance_exempt = False
    record.record_datetime = datetime(2026, 7, 24, 8, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    record.is_verified = False
    record.record_type = RecordType.ENTRY
    return record


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.entry_1 = time(8, 0)
    return config


@pytest.fixture
def tolerance_service():
    return ToleranceCronService()


def test_process_entry_record_exempt(tolerance_service, db_session_mock, base_record):
    base_record.user.is_tolerance_exempt = True
    tolerance_service._process_entry_record(db_session_mock, base_record, datetime.now(), ZoneInfo("America/Sao_Paulo"))
    assert base_record.is_verified is True


def test_process_entry_record_no_config(tolerance_service, db_session_mock, base_record):
    db_session_mock.query.return_value = make_query_mock([])
    tolerance_service._process_entry_record(db_session_mock, base_record, datetime.now(), ZoneInfo("America/Sao_Paulo"))
    assert base_record.is_verified is True


def test_process_entry_record_no_entry_1(tolerance_service, db_session_mock, base_record, mock_config):
    mock_config.entry_1 = None
    db_session_mock.query.return_value = make_query_mock([mock_config])
    tolerance_service._process_entry_record(db_session_mock, base_record, datetime.now(), ZoneInfo("America/Sao_Paulo"))
    assert base_record.is_verified is True


def test_process_entry_record_not_first_entry(tolerance_service, db_session_mock, base_record, mock_config):
    db_session_mock.query.side_effect = [
        make_query_mock([mock_config]),
        make_query_mock([MagicMock(id=2)])
    ]
    tolerance_service._process_entry_record(db_session_mock, base_record, datetime.now(), ZoneInfo("America/Sao_Paulo"))
    assert base_record.is_verified is True


def test_process_entry_record_diff_less_than_5(tolerance_service, db_session_mock, base_record, mock_config):
    db_session_mock.query.side_effect = [
        make_query_mock([mock_config]),
        make_query_mock([])
    ]
    tz = ZoneInfo("America/Sao_Paulo")
    base_record.record_datetime = datetime(2026, 7, 24, 7, 56, tzinfo=tz)
    tolerance_service._process_entry_record(db_session_mock, base_record, datetime.now(tz), tz)
    assert base_record.is_verified is True


def test_process_entry_record_diff_greater_than_5_now_less(tolerance_service, db_session_mock, base_record,
                                                           mock_config):
    db_session_mock.query.side_effect = [
        make_query_mock([mock_config]),
        make_query_mock([])
    ]
    tz = ZoneInfo("America/Sao_Paulo")
    base_record.record_datetime = datetime(2026, 7, 24, 7, 50, tzinfo=tz)
    now = datetime(2026, 7, 24, 7, 55, tzinfo=tz)
    tolerance_service._process_entry_record(db_session_mock, base_record, now, tz)
    assert base_record.is_verified is False


def test_process_entry_record_diff_greater_than_5_existing_adj(tolerance_service, db_session_mock, base_record,
                                                               mock_config):
    db_session_mock.query.side_effect = [
        make_query_mock([mock_config]),
        make_query_mock([]),
        make_query_mock([MagicMock()])
    ]
    tz = ZoneInfo("America/Sao_Paulo")
    base_record.record_datetime = datetime(2026, 7, 24, 7, 50, tzinfo=tz)
    now = datetime(2026, 7, 24, 8, 10, tzinfo=tz)
    tolerance_service._process_entry_record(db_session_mock, base_record, now, tz)
    assert base_record.is_verified is True
    db_session_mock.add.assert_not_called()


def test_process_entry_record_diff_greater_than_5_no_adj(tolerance_service, db_session_mock, base_record, mock_config):
    db_session_mock.query.side_effect = [
        make_query_mock([mock_config]),
        make_query_mock([]),
        make_query_mock([])
    ]
    tz = ZoneInfo("America/Sao_Paulo")
    base_record.record_datetime = datetime(2026, 7, 24, 7, 50, tzinfo=tz)
    base_record.record_datetime = base_record.record_datetime.replace(tzinfo=None)
    now = datetime(2026, 7, 24, 8, 10, tzinfo=tz)
    tolerance_service._process_entry_record(db_session_mock, base_record, now, tz)
    assert base_record.is_verified is True
    db_session_mock.add.assert_not_called()


def test_process_unverified_entries_success(tolerance_service, db_session_mock, base_record, mocker):
    class ContextManagerMock:
        def __enter__(self):
            return db_session_mock

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    mocker.patch("app.shared.tolerance_cron_service.get_db_session", return_value=ContextManagerMock())
    db_session_mock.query.return_value = make_query_mock([base_record])
    mocker.patch.object(tolerance_service, "_process_entry_record")
    tolerance_service.process_unverified_entries()
    tolerance_service._process_entry_record.assert_called_once()
    db_session_mock.commit.assert_called_once()


def test_process_unverified_entries_sqlalchemy_error(tolerance_service, db_session_mock, mocker):
    class ContextManagerMock:
        def __enter__(self):
            return db_session_mock

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    mocker.patch("app.shared.tolerance_cron_service.get_db_session", return_value=ContextManagerMock())
    db_session_mock.query.side_effect = SQLAlchemyError("DB Error")
    mock_logger = mocker.patch("app.shared.tolerance_cron_service.logger")
    tolerance_service.process_unverified_entries()
    mock_logger.exception.assert_called_once()


def test_process_unverified_entries_exception(tolerance_service, db_session_mock, mocker):
    class ContextManagerMock:
        def __enter__(self):
            return db_session_mock

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    mocker.patch("app.shared.tolerance_cron_service.get_db_session", return_value=ContextManagerMock())
    db_session_mock.query.side_effect = Exception("General Error")
    mock_logger = mocker.patch("app.shared.tolerance_cron_service.logger")
    tolerance_service.process_unverified_entries()
    mock_logger.exception.assert_called_once()


def test_reprocess_historical_entries(tolerance_service, db_session_mock, base_record, mocker):
    db_session_mock.query.return_value = make_query_mock([base_record])
    mocker.patch.object(tolerance_service, "_process_entry_record")
    start_date = date(2026, 7, 1)
    end_date = date(2026, 7, 31)
    user_ids = [1]
    tolerance_service.reprocess_historical_entries(db_session_mock, start_date, end_date, user_ids)
    tolerance_service._process_entry_record.assert_called_once()
    db_session_mock.commit.assert_called_once()


def test_process_unverified_entries_exit_record(tolerance_service, db_session_mock, base_record, mocker):
    class ContextManagerMock:
        def __enter__(self):
            return db_session_mock

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    mocker.patch("app.shared.tolerance_cron_service.get_db_session", return_value=ContextManagerMock())
    base_record.record_type = RecordType.EXIT
    base_record.is_verified = False
    db_session_mock.query.return_value = make_query_mock([base_record])
    tolerance_service.process_unverified_entries()
    assert base_record.is_verified is True
    db_session_mock.commit.assert_called_once()


def test_reprocess_historical_entries_exit_record(tolerance_service, db_session_mock, base_record):
    base_record.record_type = RecordType.EXIT
    base_record.is_verified = False
    db_session_mock.query.return_value = make_query_mock([base_record])
    start_date = date(2026, 7, 1)
    end_date = date(2026, 7, 31)
    user_ids = [1]
    tolerance_service.reprocess_historical_entries(db_session_mock, start_date, end_date, user_ids)
    assert base_record.is_verified is True
    db_session_mock.commit.assert_called_once()


@pytest.mark.asyncio
async def test_async_process_entry_record_branches(tolerance_service, base_record, mock_config):
    from unittest.mock import AsyncMock
    tz = ZoneInfo("America/Sao_Paulo")
    now = datetime(2026, 7, 24, 9, 0, tzinfo=tz)
    async_db = AsyncMock()

    base_record.user.is_tolerance_exempt = True
    await tolerance_service.async_process_entry_record(async_db, base_record, now, tz)
    assert base_record.is_verified is True

    base_record.user.is_tolerance_exempt = False
    base_record.is_verified = False
    async_db.scalar.return_value = None
    await tolerance_service.async_process_entry_record(async_db, base_record, now, tz)
    assert base_record.is_verified is True

    base_record.is_verified = False
    other_entry = MagicMock()
    other_entry.id = 999
    async_db.scalar.side_effect = [mock_config, other_entry]
    await tolerance_service.async_process_entry_record(async_db, base_record, now, tz)
    assert base_record.is_verified is True

    base_record.is_verified = False
    base_record.record_datetime = datetime(2026, 7, 24, 7, 57, tzinfo=tz)
    async_db.scalar.side_effect = [mock_config, base_record]
    await tolerance_service.async_process_entry_record(async_db, base_record, now, tz)
    assert base_record.is_verified is True

    base_record.is_verified = False
    base_record.record_datetime = datetime(2026, 7, 24, 7, 30, tzinfo=tz)
    async_db.scalar.side_effect = [mock_config, base_record]
    await tolerance_service.async_process_entry_record(async_db, base_record, now, tz)
    assert base_record.is_verified is True

    base_record.is_verified = False
    base_record.record_datetime = datetime(2026, 7, 24, 8, 0)
    async_db.scalar.side_effect = [mock_config, base_record]
    await tolerance_service.async_process_entry_record(async_db, base_record, now, tz)
    assert base_record.is_verified is True


@pytest.mark.asyncio
async def test_async_reprocess_historical_entries(tolerance_service, base_record):
    from unittest.mock import AsyncMock
    tz = ZoneInfo("America/Sao_Paulo")
    async_db = AsyncMock()

    exit_record = MagicMock()
    exit_record.record_type = RecordType.EXIT
    exit_record.is_verified = False

    base_record.record_type = RecordType.ENTRY
    base_record.is_verified = False

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [base_record, exit_record]
    async_db.scalars.return_value = mock_scalars

    mock_config = MagicMock()
    mock_config.entry_1 = time(8, 0)
    async_db.scalar.side_effect = [mock_config, base_record]

    await tolerance_service.async_reprocess_historical_entries(
        db=async_db,
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 31),
        user_ids=[1],
    )
    assert exit_record.is_verified is True
    assert base_record.is_verified is True
    async_db.commit.assert_called_once()
