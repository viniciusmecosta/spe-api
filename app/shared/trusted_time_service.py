import asyncio
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import ntplib

from app.core.config import settings


class NTPException(Exception):
    pass


class TrustedTimeService:

    def __init__(self) -> None:
        self._ntp_offset: float | None = None
        self._last_ntp_sync: datetime | None = None
        self._ntp_lock = threading.RLock()
        self._is_syncing: bool = False
        self._sync_thread: threading.Thread | None = None

    def reset_ntp_cache(self) -> None:
        with self._ntp_lock:
            self._ntp_offset = None
            self._last_ntp_sync = None
            self._is_syncing = False
            self._sync_thread = None

    def get_trusted_time(self) -> tuple[datetime, bool]:
        now_utc = self._get_current_utc_time()
        needs_sync = self._check_if_sync_needed(now_utc)
        if needs_sync:
            if self._ntp_offset is not None:
                self._trigger_background_sync(now_utc)
            else:
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

    def _trigger_background_sync(self, now_utc: datetime) -> None:
        with self._ntp_lock:
            if self._is_syncing:
                return
            self._is_syncing = True
            self._last_ntp_sync = now_utc
            thread = threading.Thread(target=self._run_background_sync, args=(now_utc,), daemon=True)
            self._sync_thread = thread
            thread.start()

    def _run_background_sync(self, now_utc: datetime) -> None:
        try:
            self._execute_ntp_request(now_utc)
        finally:
            with self._ntp_lock:
                self._is_syncing = False

    def _perform_sync_with_lock(self, force: bool = False) -> None:
        with self._ntp_lock:
            now_utc_locked = self._get_current_utc_time()
            if force or self._check_if_sync_needed(now_utc_locked):
                self._execute_ntp_request(now_utc_locked)

    async def sync_ntp_async(self) -> None:
        await asyncio.to_thread(self._perform_sync_with_lock, True)

    def _execute_ntp_request(self, now_utc_locked: datetime) -> None:
        try:
            client = ntplib.NTPClient()
            response = self._request_ntp_from_servers(client)
            with self._ntp_lock:
                if response:
                    utc_ntp = datetime.fromtimestamp(response.tx_time, ZoneInfo("UTC"))
                    self._ntp_offset = (utc_ntp - now_utc_locked).total_seconds()
                    self._last_ntp_sync = now_utc_locked
                else:
                    raise NTPException("NTP_FAILED")
        except Exception as e:
            import logging
            logging.error(f"Failed to sync NTP: {e}")
            with self._ntp_lock:
                self._ntp_offset = None
                self._last_ntp_sync = now_utc_locked

    def _request_ntp_from_servers(self, client: ntplib.NTPClient) -> ntplib.NTPStats | None:
        for server in ["pool.ntp.br", "pool.ntp.org", "time.google.com"]:
            try:
                return client.request(server, version=3, timeout=2.0)
            except Exception:
                continue
        return None


trusted_time_service = TrustedTimeService()
