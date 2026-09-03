from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo

import pytest
from app.core.config import settings
from app.shared.trusted_time_service import trusted_time_service


def test_get_trusted_time_cache_hit():
    trusted_time_service.reset_ntp_cache()
    now_utc = datetime.now(ZoneInfo("UTC"))
    trusted_time_service._last_ntp_sync = now_utc - timedelta(minutes=30)
    trusted_time_service._ntp_offset = 5.0
    with patch("ntplib.NTPClient") as mock_ntp:
        time_result, is_trusted = trusted_time_service.get_trusted_time()
        mock_ntp.assert_not_called()
        assert is_trusted is True
        assert isinstance(time_result, datetime)
        assert time_result.tzinfo == ZoneInfo(settings.TIMEZONE)


def test_get_trusted_time_cache_failed_recent():
    trusted_time_service.reset_ntp_cache()
    now_utc = datetime.now(ZoneInfo("UTC"))
    trusted_time_service._last_ntp_sync = now_utc - timedelta(seconds=30)
    trusted_time_service._ntp_offset = None
    with patch("ntplib.NTPClient") as mock_ntp:
        time_result, is_trusted = trusted_time_service.get_trusted_time()
        mock_ntp.assert_not_called()
        assert is_trusted is False
        assert isinstance(time_result, datetime)


def test_get_trusted_time_double_checked_locking():
    trusted_time_service.reset_ntp_cache()

    class FakeLock:

        def __enter__(self):
            trusted_time_service._last_ntp_sync = datetime.now(ZoneInfo("UTC")) - timedelta(seconds=10)
            trusted_time_service._ntp_offset = 10.0
            return self

        def __exit__(self, *args):
            pass

    original_lock = trusted_time_service._ntp_lock
    trusted_time_service._ntp_lock = FakeLock()
    try:
        with patch("ntplib.NTPClient") as mock_ntp:
            time_result, is_trusted = trusted_time_service.get_trusted_time()
            mock_ntp.assert_not_called()
            assert is_trusted is True
            assert trusted_time_service._ntp_offset == 10.0
    finally:
        trusted_time_service._ntp_lock = original_lock


def test_get_trusted_time_double_checked_locking_failure_recent():
    trusted_time_service.reset_ntp_cache()

    class FakeLock:

        def __enter__(self):
            trusted_time_service._last_ntp_sync = datetime.now(ZoneInfo("UTC")) - timedelta(seconds=10)
            trusted_time_service._ntp_offset = None
            return self

        def __exit__(self, *args):
            pass

    original_lock = trusted_time_service._ntp_lock
    trusted_time_service._ntp_lock = FakeLock()
    try:
        with patch("ntplib.NTPClient") as mock_ntp:
            time_result, is_trusted = trusted_time_service.get_trusted_time()
            mock_ntp.assert_not_called()
            assert is_trusted is False
    finally:
        trusted_time_service._ntp_lock = original_lock


def test_get_trusted_time_success():
    trusted_time_service.reset_ntp_cache()
    with patch("ntplib.NTPClient") as mock_ntp:
        mock_client_instance = mock_ntp.return_value
        mock_response = MagicMock()
        mock_response.tx_time = 1627819200.0
        mock_client_instance.request.return_value = mock_response
        time, is_trusted = trusted_time_service.get_trusted_time()
        assert is_trusted is True
        assert isinstance(time, datetime)


def test_get_trusted_time_failure():
    trusted_time_service.reset_ntp_cache()

    with patch("ntplib.NTPClient") as mock_ntp:
        mock_client_instance = mock_ntp.return_value
        mock_client_instance.request.side_effect = Exception("NTP error")

        time, is_trusted = trusted_time_service.get_trusted_time()

        assert is_trusted is False
        assert isinstance(time, datetime)


def test_get_trusted_time_cache_expired():
    trusted_time_service.reset_ntp_cache()
    now_utc = datetime.now(ZoneInfo("UTC"))
    trusted_time_service._last_ntp_sync = now_utc - timedelta(hours=2)
    trusted_time_service._ntp_offset = 5.0
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


def test_get_trusted_time_background_sync_already_running():
    trusted_time_service.reset_ntp_cache()
    now_utc = datetime.now(ZoneInfo("UTC"))
    trusted_time_service._last_ntp_sync = now_utc - timedelta(hours=2)
    trusted_time_service._ntp_offset = 5.0
    trusted_time_service._is_syncing = True
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
