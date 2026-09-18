import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.shared.trusted_time_service import trusted_time_service


def test_get_trusted_time_cache_hit(monkeypatch):
    trusted_time_service.reset_ntp_cache()
    now_utc = datetime.now(ZoneInfo("UTC"))
    monkeypatch.setattr(trusted_time_service, "_last_ntp_sync", now_utc - timedelta(minutes=30))
    monkeypatch.setattr(trusted_time_service, "_ntp_offset", 5.0)
    with patch("ntplib.NTPClient") as mock_ntp:
        time_result, is_trusted = trusted_time_service.get_trusted_time()
        mock_ntp.assert_not_called()
        assert is_trusted is True
        assert isinstance(time_result, datetime)
        assert time_result.tzinfo == ZoneInfo(settings.TIMEZONE)


def test_get_trusted_time_cache_failed_recent(monkeypatch):
    trusted_time_service.reset_ntp_cache()
    now_utc = datetime.now(ZoneInfo("UTC"))
    monkeypatch.setattr(trusted_time_service, "_last_ntp_sync", now_utc - timedelta(seconds=30))
    monkeypatch.setattr(trusted_time_service, "_ntp_offset", None)
    with patch("ntplib.NTPClient") as mock_ntp:
        time_result, is_trusted = trusted_time_service.get_trusted_time()
        mock_ntp.assert_not_called()
        assert is_trusted is False
        assert isinstance(time_result, datetime)


def test_get_trusted_time_double_checked_locking(monkeypatch):
    trusted_time_service.reset_ntp_cache()

    class FakeLock:

        def __enter__(self):
            monkeypatch.setattr(trusted_time_service, "_last_ntp_sync",
                                datetime.now(ZoneInfo("UTC")) - timedelta(seconds=10))
            monkeypatch.setattr(trusted_time_service, "_ntp_offset", 10.0)
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(trusted_time_service, "_ntp_lock", FakeLock())
    with patch("ntplib.NTPClient") as mock_ntp:
        time_result, is_trusted = trusted_time_service.get_trusted_time()
        mock_ntp.assert_not_called()
        assert is_trusted is True
        assert trusted_time_service._ntp_offset == 10.0


def test_get_trusted_time_double_checked_locking_failure_recent(monkeypatch):
    trusted_time_service.reset_ntp_cache()

    class FakeLock:

        def __enter__(self):
            monkeypatch.setattr(trusted_time_service, "_last_ntp_sync",
                                datetime.now(ZoneInfo("UTC")) - timedelta(seconds=10))
            monkeypatch.setattr(trusted_time_service, "_ntp_offset", None)
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(trusted_time_service, "_ntp_lock", FakeLock())
    with patch("ntplib.NTPClient") as mock_ntp:
        time_result, is_trusted = trusted_time_service.get_trusted_time()
        mock_ntp.assert_not_called()
        assert is_trusted is False


def test_get_trusted_time_success():
    trusted_time_service.reset_ntp_cache()
    with patch("ntplib.NTPClient") as mock_ntp:
        mock_client_instance = mock_ntp.return_value
        mock_response = MagicMock()
        mock_response.tx_time = 1627819200.0
        mock_client_instance.request.return_value = mock_response
        time, is_trusted = trusted_time_service.get_trusted_time()
        assert is_trusted is False
        assert isinstance(time, datetime)
        if trusted_time_service._sync_thread:
            trusted_time_service._sync_thread.join(timeout=2.0)
        time_after, is_trusted_after = trusted_time_service.get_trusted_time()
        assert is_trusted_after is True
        assert isinstance(time_after, datetime)


def test_get_trusted_time_failure():
    trusted_time_service.reset_ntp_cache()

    with patch("ntplib.NTPClient") as mock_ntp:
        mock_client_instance = mock_ntp.return_value
        mock_client_instance.request.side_effect = Exception("NTP error")

        time, is_trusted = trusted_time_service.get_trusted_time()

        assert is_trusted is False
        assert isinstance(time, datetime)


def test_get_trusted_time_cache_expired(monkeypatch):
    trusted_time_service.reset_ntp_cache()
    now_utc = datetime.now(ZoneInfo("UTC"))
    monkeypatch.setattr(trusted_time_service, "_last_ntp_sync", now_utc - timedelta(hours=2))
    monkeypatch.setattr(trusted_time_service, "_ntp_offset", 5.0)
    with patch("ntplib.NTPClient") as mock_ntp:
        mock_client_instance = mock_ntp.return_value
        mock_response = MagicMock()
        mock_response.tx_time = 1627819200.0
        mock_client_instance.request.return_value = mock_response

        time_result, is_trusted = trusted_time_service.get_trusted_time()
        if trusted_time_service._sync_thread:
            trusted_time_service._sync_thread.join(timeout=2.0)
        mock_ntp.assert_called_once()
        assert is_trusted is True


def test_get_trusted_time_background_sync_already_running(monkeypatch):
    trusted_time_service.reset_ntp_cache()
    now_utc = datetime.now(ZoneInfo("UTC"))
    monkeypatch.setattr(trusted_time_service, "_last_ntp_sync", now_utc - timedelta(hours=2))
    monkeypatch.setattr(trusted_time_service, "_ntp_offset", 5.0)
    monkeypatch.setattr(trusted_time_service, "_is_syncing", True)
    with patch("ntplib.NTPClient") as mock_ntp:
        time_result, is_trusted = trusted_time_service.get_trusted_time()
        mock_ntp.assert_not_called()
        assert is_trusted is True


@pytest.mark.asyncio
async def test_sync_ntp_async():
    trusted_time_service.reset_ntp_cache()
    with patch("ntplib.NTPClient") as mock_ntp:
        mock_client_instance = mock_ntp.return_value
        mock_response = MagicMock()
        mock_response.tx_time = 1627819200.0
        mock_client_instance.request.return_value = mock_response

        await trusted_time_service.sync_ntp_async()
        mock_ntp.assert_called_once()
        assert trusted_time_service._ntp_offset is not None


@pytest.mark.asyncio
async def test_sync_ntp_with_backoff_async_success(mocker, monkeypatch):
    trusted_time_service.reset_ntp_cache()
    mock_sync = mocker.patch.object(trusted_time_service, "sync_ntp_async")

    async def fake_sync():
        monkeypatch.setattr(trusted_time_service, "_ntp_offset", 1.0)

    mock_sync.side_effect = fake_sync
    result = await trusted_time_service.sync_ntp_with_backoff_async(initial_delay=0.01)
    assert result is True
    assert mock_sync.call_count == 1


@pytest.mark.asyncio
async def test_sync_ntp_with_backoff_async_retry_then_succeed(mocker, monkeypatch):
    trusted_time_service.reset_ntp_cache()
    mock_sync = mocker.patch.object(trusted_time_service, "sync_ntp_async")
    mock_sleep = mocker.patch("asyncio.sleep")
    calls = 0

    async def fake_sync():
        nonlocal calls
        calls += 1
        if calls >= 2:
            monkeypatch.setattr(trusted_time_service, "_ntp_offset", 2.0)

    mock_sync.side_effect = fake_sync
    result = await trusted_time_service.sync_ntp_with_backoff_async(initial_delay=0.1, backoff_factor=2.0)
    assert result is True
    assert calls == 2
    mock_sleep.assert_called_once_with(0.1)


@pytest.mark.asyncio
async def test_sync_ntp_with_backoff_async_max_attempts(mocker):
    trusted_time_service.reset_ntp_cache()
    mocker.patch.object(trusted_time_service, "sync_ntp_async")
    mocker.patch("asyncio.sleep")
    result = await trusted_time_service.sync_ntp_with_backoff_async(
        initial_delay=0.1, max_attempts=3, backoff_factor=2.0
    )
    assert result is False


@pytest.mark.asyncio
async def test_sync_ntp_with_backoff_async_cancelled(mocker):
    import asyncio
    trusted_time_service.reset_ntp_cache()
    mocker.patch.object(trusted_time_service, "sync_ntp_async")
    mocker.patch("asyncio.sleep", side_effect=asyncio.CancelledError)
    with pytest.raises(asyncio.CancelledError):
        await trusted_time_service.sync_ntp_with_backoff_async(initial_delay=0.1)

