import json
from calendar import monthrange
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.features.reports.report_exceptions import ReportUserNotFoundError
from app.features.reports.report_service import ReportService
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import User
from app.shared import deps

ExportKind = Literal["marcacoes", "jornada"]
MAX_RECORDS = 5000
NOTICE = (
    "Exportação operacional sem valor fiscal: não é AFD nem AEJ, "
    "sem assinatura digital e sem garantia de inviolabilidade."
)


class OperationalExportService:
    def __init__(self, db: Annotated[AsyncSession, Depends(deps.get_async_db)]):
        self.db = db

    async def export(self, kind: ExportKind, user_id: int, month: int, year: int, user: User) -> Response:
        employee = await self.db.get(User, user_id)
        if employee is None:
            raise ReportUserNotFoundError(user_id=user_id)
        tz = ZoneInfo(settings.TIMEZONE)
        first = date(year, month, 1)
        last = date(year, month, monthrange(year, month)[1])
        start = datetime.combine(first, time.min, tzinfo=tz)
        end = datetime.combine(last + timedelta(days=1), time.min, tzinfo=tz)
        statement = (
            select(TimeRecord)
            .where(TimeRecord.user_id == user_id, TimeRecord.record_datetime >= start, TimeRecord.record_datetime < end)
            .order_by(TimeRecord.record_datetime, TimeRecord.id)
            .limit(MAX_RECORDS + 1)
        )
        records = list((await self.db.scalars(statement)).all())
        if len(records) > MAX_RECORDS:
            raise HTTPException(status_code=422, detail="Período excede o limite de registros para exportação.")

        payload = {
            "aviso": NOTICE,
            "tipo": kind,
            "gerado_em": datetime.now(UTC).isoformat(),
            "fuso_horario": settings.TIMEZONE,
            "periodo": {"inicio": first.isoformat(), "fim": last.isoformat()},
            "usuario": {"id": employee.id, "nome": employee.name},
        }
        if kind == "marcacoes":
            payload["marcacoes"] = [
                {
                    "id": record.id,
                    "data_hora": record.record_datetime.astimezone(tz).isoformat(),
                    "tipo": record.record_type.value,
                    "dispositivo": record.device_name,
                    "ignorada": record.is_ignored,
                    "excluida_em": record.deleted_at.isoformat() if record.deleted_at else None,
                    "registro_original_id": record.original_record_id,
                    "ajuste_origem_id": record.source_adjustment_id,
                }
                for record in records
            ]
        else:
            report = await ReportService(self.db).get_advanced_user_report_or_404(
                user_id=user_id, month=month, year=year, current_user=user,
            )
            payload["jornada"] = report.model_dump(mode="json")
        filename = f"operacional_{kind}_{user_id}_{year:04d}{month:02d}.json"
        return Response(
            content=json.dumps(jsonable_encoder(payload), ensure_ascii=False),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"},
        )
