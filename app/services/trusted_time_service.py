import ntplib
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings


class NTPException(Exception):
    pass


class TrustedTimeService:

    def __init__(self) -> None:
        self._ntp_offset: float | None = None
        self._last_ntp_sync: datetime | None = None
        self._ntp_lock = threading.Lock()

    def reset_ntp_cache(self) -> None:
        with self._ntp_lock:
            self._ntp_offset = None
            self._last_ntp_sync = None

    def get_trusted_time(self) -> tuple[datetime, bool]:
        now_utc = self._get_current_utc_time()
        needs_sync = self._check_if_sync_needed(now_utc)
        if needs_sync:
            self._perform_sync_with_lock()
        if self._ntp_offset is not None:
            trusted_utc = self._get_current_utc_time() + timedelta(seconds=self._ntp_offset)
            return (trusted_utc.astimezone(ZoneInfo(settings.TIMEZONE)), True)
        return (datetime.now(ZoneInfo(settings.TIMEZONE)), False)

    def _get_current_utc_time(self) -> datetime:
        return datetime.now(ZoneInfo("UTC"))

    def _check_if_sync_needed(self, now_utc: datetime) -> bool:
        if self._last_ntp_sync is None:
            return True
        elapsed = (now_utc - self._last_ntp_sync).total_seconds()
        if self._ntp_offset is not None and elapsed < 3600.0:
            return False
        if self._ntp_offset is None and elapsed < 60.0:
            return False
        return True

    def _perform_sync_with_lock(self) -> None:
        with self._ntp_lock:
            now_utc_locked = self._get_current_utc_time()
            if self._check_if_sync_needed(now_utc_locked):
                self._execute_ntp_request(now_utc_locked)

    def _execute_ntp_request(self, now_utc_locked: datetime) -> None:
        try:
            client = ntplib.NTPClient()
            response = self._request_ntp_from_servers(client)
            if response:
                utc_ntp = datetime.fromtimestamp(response.tx_time, ZoneInfo("UTC"))
                self._ntp_offset = (utc_ntp - now_utc_locked).total_seconds()
                self._last_ntp_sync = now_utc_locked
            else:
                raise NTPException("NTP_FAILED")
        except Exception:
            self._ntp_offset = None
            self._last_ntp_sync = now_utc_locked

    def _request_ntp_from_servers(self, client: ntplib.NTPClient) -> ntplib.NTPStats | None:
        for server in ["pool.ntp.br", "pool.ntp.org", "time.google.com"]:
            try:
                return client.request(server, version=3, timeout=0.5)
            except Exception:
                continue
        return None


trusted_time_service = TrustedTimeService()
