from calendar import monthrange
from datetime import date, datetime, time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.features.companies.company_models import Company
from app.features.reports.report_exceptions import ReportUserNotFoundError
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import User, UserWorkScheduleConfig
from app.shared import deps
from app.shared.enums import RecordType

BATCH_SIZE = 1000


def _field(value: object | None) -> str:
    result = str(value) if value is not None else ""
    if any(char in result for char in "|\r\n"):
        raise HTTPException(status_code=422, detail="Dados contêm caracteres incompatíveis com o formato textual.")
    return result


def _date_time(value: datetime, zone: ZoneInfo) -> str:
    return value.astimezone(zone).strftime("%Y-%m-%dT%H:%M:00%z")


def _time(value: time | None) -> str:
    return value.strftime("%H%M") if value else ""


def _line(*values: object) -> str:
    return "|".join(_field(value) for value in values)


def _schedule_for_day(schedules: list[UserWorkScheduleConfig], day: date) -> UserWorkScheduleConfig | None:
    matches = [item for item in schedules if item.day_of_week == day.weekday()
               and item.valid_from <= day and (item.valid_until is None or item.valid_until >= day)]
    return matches[0] if len(matches) == 1 else None


def _record_code(ignored: bool, is_entry: bool) -> str:
    if ignored:
        return "D"
    if is_entry:
        return "E"
    return "S"


def _record_lines(
    employee_id: int, records: list[TimeRecord], schedules: list[UserWorkScheduleConfig], zone: ZoneInfo,
) -> list[str]:
    lines = []
    counters: dict[date, int] = {}
    for record in records:
        day = record.record_datetime.astimezone(zone).date()
        ignored = record.is_ignored or record.deleted_at is not None
        is_entry = record.record_type == RecordType.ENTRY
        if not ignored and is_entry:
            counters[day] = counters.get(day, 0) + 1
        sequence = counters.get(day, 0)
        code = _record_code(ignored, is_entry)
        source = "I" if record.edited_by or record.original_record_id or record.source_adjustment_id else "T"
        schedule = _schedule_for_day(schedules, day) if not ignored and is_entry and sequence == 1 else None
        lines.append(_line("05", employee_id, _date_time(record.record_datetime, zone), "", code,
                           f"{sequence:03}" if 0 < sequence <= 999 else "", source,
                           schedule.id if schedule else "", record.edit_justification))
    return lines


class AejPreviewService:
    def __init__(self, db: Annotated[AsyncSession, Depends(deps.get_async_db)]):
        self.db = db

    async def _records(self, user_id: int, start: datetime, end: datetime) -> list[TimeRecord]:
        records: list[TimeRecord] = []
        cursor: tuple[datetime, int] | None = None
        while True:
            query = select(TimeRecord).where(
                TimeRecord.user_id == user_id, TimeRecord.record_datetime >= start,
                TimeRecord.record_datetime < end,
            )
            if cursor is not None:
                query = query.where(tuple_(TimeRecord.record_datetime, TimeRecord.id) > cursor)
            query = query.order_by(TimeRecord.record_datetime, TimeRecord.id).limit(BATCH_SIZE)
            batch = list((await self.db.scalars(query)).all())
            records.extend(batch)
            if len(batch) < BATCH_SIZE:
                return records
            cursor = (batch[-1].record_datetime, batch[-1].id)

    async def export(self, user_id: int, month: int, year: int) -> Response:
        employee = await self.db.get(User, user_id)
        if employee is None:
            raise ReportUserNotFoundError(user_id=user_id)
        company = (await self.db.scalars(select(Company))).first()
        if company is None:
            raise HTTPException(status_code=422, detail="Cadastre a empresa antes de gerar a prévia.")
        first = date(year, month, 1)
        last = date(year, month, monthrange(year, month)[1])
        zone = ZoneInfo(settings.TIMEZONE)
        start = datetime.combine(first, time.min, tzinfo=zone)
        end = datetime.combine(last + timedelta(days=1), time.min, tzinfo=zone)
        schedules = list((await self.db.scalars(select(UserWorkScheduleConfig).where(
            UserWorkScheduleConfig.user_id == user_id,
            UserWorkScheduleConfig.valid_from <= last,
            or_(UserWorkScheduleConfig.valid_until.is_(None), UserWorkScheduleConfig.valid_until >= first),
        ).order_by(UserWorkScheduleConfig.id))).all())
        records = await self._records(user_id, start, end)
        company_id = "".join(c for c in (company.cnpj or "") if c.isdigit())
        cpf = "".join(c for c in (employee.cpf or "") if c.isdigit())
        lines = [
            _line("01", "1" if company_id else "", company_id, "", "", company.name,
                  first.isoformat(), last.isoformat(), _date_time(datetime.now(zone), zone), "002"),
            _line("03", employee.id, cpf, employee.name),
        ]
        for schedule in schedules:
            lines.append(_line("04", schedule.id, schedule.daily_minutes, _time(schedule.entry_1),
                               _time(schedule.exit_1), _time(schedule.entry_2), _time(schedule.exit_2)))
        lines.extend(_record_lines(employee.id, records, schedules, zone))
        lines.append(_line("99", 1, 0, 1, len(schedules), len(records), 0, 0, 0))
        try:
            content = ("\r\n".join(lines) + "\r\n").encode("iso-8859-1")
        except UnicodeEncodeError as exc:
            raise HTTPException(status_code=422, detail="Dados contêm caracteres incompatíveis com ISO-8859-1.") from exc
        return Response(content=content, media_type="text/plain; charset=iso-8859-1", headers={
            "Content-Disposition": f'attachment; filename="rascunho_nao_fiscal_jornada_{user_id}_{year:04}{month:02}.txt"',
            "Cache-Control": "no-store",
            "X-Export-Status": "draft-not-fiscal-unsigned-incomplete",
            "X-Export-Limitations": "night-hours-unverified",
        })
