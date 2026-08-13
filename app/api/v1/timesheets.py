from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api import deps
from app.services.timesheet_service import timesheet_service

router = APIRouter()


def validate_date_not_future(month: int, year: int) -> None:
    now = datetime.now()
    if year > now.year or (year == now.year and month > now.month):
        raise HTTPException(
            status_code=400,
            detail="Não é possível solicitar espelhos de ponto referentes a meses futuros.",
        )


@router.get(
    "/user/{user_id}/pdf",
    dependencies=[Depends(deps.get_current_manager)],
    responses={
        400: {"description": "Não é possível solicitar espelhos de ponto referentes a meses futuros."},
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
        404: {"description": "Dados do usuário não encontrados"},
        422: {"description": "Erro de validação de parâmetros"},
    },
)
def get_official_timesheet_user_pdf(
    user_id: int,
    db: Annotated[Session, Depends(deps.get_db)],
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000),
) -> StreamingResponse:
    validate_date_not_future(month, year)
    pdf_buffer = timesheet_service.generate_user_timesheet_pdf(db, user_id, month, year)
    filename = f"espelho_ponto_{user_id}_{month:02d}_{year}.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get(
    "/all/pdf",
    dependencies=[Depends(deps.get_current_manager)],
    responses={
        400: {"description": "Não é possível solicitar espelhos de ponto referentes a meses futuros."},
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
        422: {"description": "Erro de validação de parâmetros"},
    },
)
def get_official_timesheet_all_pdf(
    db: Annotated[Session, Depends(deps.get_db)],
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000),
    employee_ids: list[int] | None = Query(None),
) -> StreamingResponse:
    validate_date_not_future(month, year)
    zip_buffer = timesheet_service.generate_all_timesheets_pdf_zip(db, month, year, employee_ids)
    filename = f"espelhos_ponto_lote_{month:02d}_{year}.zip"

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
