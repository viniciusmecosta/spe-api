import html
import logging
import secrets
import time as clock
from datetime import date
from html.parser import HTMLParser
from typing import Annotated

import requests
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.features.system.delivery_result import DeliveryResult
from app.features.system.system_exceptions import (
    TelegramInvalidDateRangeError,
    TelegramPeriodExceededError,
)
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import User
from app.shared import deps
from app.shared.enums import RecordType
from app.shared.timezone import local_day_bounds, to_app_timezone
from app.utils.formatters import format_short_name

logger = logging.getLogger(__name__)

DATE_FORMAT = "%d/%m/%Y"


class TelegramService:
    def __init__(self, db: Annotated[AsyncSession, Depends(deps.get_async_db)] = None):
        self.db = db
        self.bot_token = settings.TELEGRAM_BOT_TOKEN
        self.chat_id = settings.TELEGRAM_CHAT_ID

    def validate_manual_report_dates(self, start_date: date, end_date: date) -> None:
        if start_date > end_date:
            raise TelegramInvalidDateRangeError()

        delta_days = (end_date - start_date).days
        if delta_days > 7:
            raise TelegramPeriodExceededError()

    @staticmethod
    def split_text(text: str, limit: int = 3500) -> list[str]:
        limit = min(max(limit, 32), 4096)
        if len(text) <= limit:
            return [text]

        class PlainText(HTMLParser):
            def __init__(self):
                super().__init__(convert_charrefs=True)
                self.parts = []

            def handle_data(self, data):
                self.parts.append(data)

        parser = PlainText()
        parser.feed(text)
        chunks, current = [], ""
        for character in "".join(parser.parts):
            escaped = html.escape(character)
            if len(current) + len(escaped) > limit:
                chunks.append(current)
                current = ""
            current += escaped
        if current:
            chunks.append(current)
        return chunks

    def _post(self, method: str, data: dict, file_path: str | None = None,
              filename: str | None = None) -> DeliveryResult:
        if not self.bot_token or not self.chat_id:
            return DeliveryResult("FAILED", "Telegram não configurado")
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/{method}"
            if file_path:
                with open(file_path, "rb") as stream:
                    response = requests.post(url, data=data,
                                             files={"document": (filename or file_path.rsplit("/", 1)[-1], stream)},
                                             timeout=(10, 60))
            else:
                response = requests.post(url, data=data, timeout=(10, 30))
            if 200 <= response.status_code < 300:
                return DeliveryResult("SUCCESS")
            if response.status_code == 429:
                try:
                    wait = int(response.json().get("parameters", {}).get("retry_after", 30))
                except (ValueError, TypeError, AttributeError):
                    wait = 30
                return DeliveryResult("RETRY", "Limite de requisições", max(1, min(wait, 86400)))
            if response.status_code in (408, 425) or response.status_code >= 500:
                return DeliveryResult("RETRY", f"Telegram HTTP {response.status_code}")
            return DeliveryResult("FAILED", f"Telegram HTTP {response.status_code}")
        except requests.exceptions.ConnectTimeout:
            return DeliveryResult("RETRY", "Timeout ao conectar ao Telegram")
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError):

            return DeliveryResult("UNCERTAIN", "Conexão interrompida; entrega precisa ser conferida")
        except (requests.exceptions.RequestException, OSError) as error:
            logger.exception("Falha no envio Telegram")
            return DeliveryResult("FAILED", type(error).__name__)

    def deliver_text(self, text: str) -> DeliveryResult:
        return self._post("sendMessage", {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"})

    def deliver_document(self, file_path: str, caption: str, filename: str | None = None) -> DeliveryResult:
        return self._post("sendDocument", {"chat_id": self.chat_id, "caption": caption[:1024]}, file_path, filename)

    @staticmethod
    def _retry(send) -> bool:
        for attempt in range(4):
            result = send()
            if result.status != "RETRY":
                return result.success
            if attempt < 3:
                clock.sleep(result.retry_after or min(30, 2 ** attempt + secrets.randbelow(1000) / 1000))
        return False

    def send_text(self, text: str) -> bool:
        return all(self._retry(lambda chunk=chunk: self.deliver_text(chunk)) for chunk in self.split_text(text))

    def send_document(self, file_path: str, caption: str, filename: str | None = None) -> bool:
        return self._retry(lambda: self.deliver_document(file_path, caption, filename))

    async def generate_report_text(self, db: AsyncSession, start_date: date, end_date: date,
                                   title_prefix: str = "Relatório Gerencial - Fechamento") -> str:
        try:
            fmt_start = start_date.strftime(DATE_FORMAT)
            fmt_end = end_date.strftime(DATE_FORMAT)

            if start_date == end_date:
                title_date = fmt_start
            else:
                title_date = f"{fmt_start} a {fmt_end}"

            text = f"<b>{html.escape(title_prefix)} {title_date}</b>\n\n"

            start_dt, _ = local_day_bounds(start_date)
            _, end_dt = local_day_bounds(end_date)

            stmt = (
                select(TimeRecord, User)
                .join(User, TimeRecord.user_id == User.id)
                .filter(TimeRecord.record_datetime >= start_dt)
                .filter(TimeRecord.record_datetime < end_dt)
                .filter(TimeRecord.is_ignored.is_(False), TimeRecord.deleted_at.is_(None))
                .order_by(TimeRecord.record_datetime, User.name)
            )
            result = await db.execute(stmt)
            records = result.all()

            if not records:
                text += "Sem registros de ponto no período."
                return text

            daily_activity = self._group_daily_activity(records)

            for d_str, users_data in daily_activity.items():
                text += f"<b>{d_str}</b>\n"
                for name, punches in users_data.items():
                    punches_str = " | ".join(punches)
                    text += f"{name} - {punches_str}\n"
                text += "\n"

            return text.strip()
        except (SQLAlchemyError, ValueError):
            logger.exception("Erro ao gerar relatório do Telegram")
            return "Erro interno ao gerar relatório gerencial."

    def _group_daily_activity(self, records) -> dict[str, dict[str, list[str]]]:
        daily_activity: dict[str, dict[str, list[str]]] = {}
        for record, user in records:
            date_str = to_app_timezone(record.record_datetime).strftime(DATE_FORMAT)
            time_str = to_app_timezone(record.record_datetime).strftime("%H:%M")
            marker = "E:" if record.record_type == RecordType.ENTRY else "S:"

            fmt_name = html.escape(format_short_name(user.name))

            if date_str not in daily_activity:
                daily_activity[date_str] = {}

            if fmt_name not in daily_activity[date_str]:
                daily_activity[date_str][fmt_name] = []

            daily_activity[date_str][fmt_name].append(f"{marker} {time_str}")

        return daily_activity


telegram_service = TelegramService()
