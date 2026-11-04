import hashlib
import json
import tempfile
from calendar import monthrange
from collections.abc import AsyncIterator, Iterator
from contextlib import ExitStack, contextmanager
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, BinaryIO, Literal
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.features.reports.report_exceptions import ReportUserNotFoundError
from app.features.reports.report_service import ReportService
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import User
from app.shared import deps
from app.shared.document_authenticity import (
    compute_operational_export_authenticity_hash,
)
from app.shared.document_signature import JSON_MARKER, new_document_mac, sign_json

ExportKind = Literal["marcacoes", "jornada"]
EXPORT_BATCH_SIZE = 1000
EXPORT_MEMORY_LIMIT = 1024 * 1024
EXPORT_READ_SIZE = 64 * 1024


def _json_bytes(value: object, *, canonical: bool = False) -> bytes:
    options = {"sort_keys": True, "separators": (",", ":")} if canonical else {}
    return json.dumps(value, ensure_ascii=False, **options).encode("utf-8")


@contextmanager
def _export_file() -> Iterator[BinaryIO]:
    with tempfile.SpooledTemporaryFile(max_size=EXPORT_MEMORY_LIMIT, mode="w+b") as file:
        yield file


async def _read_export_file(file: BinaryIO, stack: ExitStack) -> AsyncIterator[bytes]:
    with stack:
        while chunk := await run_in_threadpool(file.read, EXPORT_READ_SIZE):
            yield chunk


class OperationalExportService:
    def __init__(self, db: Annotated[AsyncSession, Depends(deps.get_async_db)]):
        self.db = db

    async def _iter_export_records(
        self, conditions: tuple, user_id: int | None, tz: ZoneInfo,
    ) -> AsyncIterator[list[dict]]:
        cursor: tuple[datetime, int] | None = None
        while True:
            if user_id is None:
                statement = select(TimeRecord, User.name).join(User, TimeRecord.user_id == User.id)
            else:
                statement = select(TimeRecord).where(TimeRecord.user_id == user_id)
            statement = statement.where(*conditions)
            if cursor is not None:
                statement = statement.where(tuple_(TimeRecord.record_datetime, TimeRecord.id) > cursor)
            statement = statement.order_by(TimeRecord.record_datetime, TimeRecord.id).limit(EXPORT_BATCH_SIZE)
            if user_id is None:
                rows = list((await self.db.execute(statement)).all())
                records = [row[0] for row in rows]
                names = {row[0].user_id: row[1] for row in rows}
            else:
                records = list((await self.db.scalars(statement)).all())
                names = {}
            yield self._serialize_marcacoes(records, names, tz, user_id is None)
            if len(records) < EXPORT_BATCH_SIZE:
                return
            cursor = (records[-1].record_datetime, records[-1].id)

    async def _export_marcacoes(
        self, payload: dict, conditions: tuple, user_id: int | None, tz: ZoneInfo, filename: str,
    ) -> StreamingResponse:
        stack = ExitStack()
        file = stack.enter_context(_export_file())
        signer = new_document_mac(b"json")
        digest = hashlib.sha256()

        def write(chunk: bytes) -> None:
            file.write(chunk)
            signer.update(chunk)

        try:
            write(b"{" + b",".join(_json_bytes(k) + b":" + _json_bytes(v) for k, v in payload.items()))
            write(b',"marcacoes":[')
            digest.update(b'{"kind":"operational_export","payload":{"fuso_horario":')
            digest.update(_json_bytes(payload["fuso_horario"], canonical=True))
            digest.update(b',"marcacoes":[')
            first = True
            async for records in self._iter_export_records(conditions, user_id, tz):
                for record in records:
                    separator = b"" if first else b","
                    write(separator + _json_bytes(record))
                    digest.update(separator + _json_bytes(record, canonical=True))
                    first = False
            write(b"]")
            digest.update(b'],"periodo":' + _json_bytes(payload["periodo"], canonical=True))
            digest.update(b',"tipo":' + _json_bytes(payload["tipo"], canonical=True))
            digest.update(b',"usuario":' + _json_bytes(payload["usuario"], canonical=True) + b"}}")
            data_hash = f"sha256:{digest.hexdigest()}"
            write(b',"metadados":' + _json_bytes({"hash_dados": data_hash}))
            signer.update(b"}")
            file.write(JSON_MARKER + signer.hexdigest().encode("ascii") + b'"}')
            length = file.tell()
            file.seek(0)
            return StreamingResponse(
                _read_export_file(file, stack), media_type="application/json", headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "Cache-Control": "no-store", "Content-Length": str(length), "X-Document-Hash": data_hash,
                },
            )
        except BaseException:
            stack.close()
            raise

    @staticmethod
    def _serialize_marcacoes(
        records: list[TimeRecord], names: dict[int | None, str], tz: ZoneInfo, include_user: bool
    ) -> list[dict]:
        return [
            {
                "id": record.id,
                "data_hora": record.record_datetime.astimezone(tz).isoformat(),
                "tipo": record.record_type.value,
                "dispositivo": record.device_name,
                "ignorada": record.is_ignored,
                "excluida_em": record.deleted_at.isoformat() if record.deleted_at else None,
                "registro_original_id": record.original_record_id,
                "ajuste_origem_id": record.source_adjustment_id,
                **({"usuario": {"id": record.user_id, "nome": names[record.user_id]}} if include_user else {}),
            }
            for record in records
        ]

    async def export(self, kind: ExportKind, user_id: int | None, month: int, year: int, user: User) -> Response:
        if user_id is None and kind == "jornada":
            raise HTTPException(status_code=422, detail="Selecione um funcionário para exportar a jornada.")
        employee = await self.db.get(User, user_id) if user_id is not None else None
        if user_id is not None and employee is None:
            raise ReportUserNotFoundError(user_id=user_id)
        tz = ZoneInfo(settings.TIMEZONE)
        first = date(year, month, 1)
        last = date(year, month, monthrange(year, month)[1])
        start = datetime.combine(first, time.min, tzinfo=tz)
        end = datetime.combine(last + timedelta(days=1), time.min, tzinfo=tz)
        payload = {
            "tipo": kind,
            "gerado_em": datetime.now(UTC).isoformat(),
            "fuso_horario": settings.TIMEZONE,
            "periodo": {"inicio": first.isoformat(), "fim": last.isoformat()},
            "usuario": {"id": employee.id, "nome": employee.name} if employee else None,
        }
        filename = f"operacional_{kind}_{user_id if user_id is not None else 'todos'}_{year:04d}{month:02d}.json"
        if kind == "marcacoes":
            return await self._export_marcacoes(
                payload, (TimeRecord.record_datetime >= start, TimeRecord.record_datetime < end), user_id, tz, filename
            )
        report = await ReportService(self.db).get_advanced_user_report_or_404(
            user_id=user_id, month=month, year=year, current_user=user,
        )
        payload["jornada"] = report.model_dump(mode="json")
        authenticity_hash = compute_operational_export_authenticity_hash(payload)
        payload["metadados"] = {"hash_dados": f"sha256:{authenticity_hash}"}
        return Response(
            content=sign_json(json.dumps(jsonable_encoder(payload), ensure_ascii=False).encode("utf-8")),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
                "X-Document-Hash": f"sha256:{authenticity_hash}",
            },
        )
