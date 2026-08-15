from typing import Annotated

from app.api import deps
from app.api.openapi_responses import (
    AUTH_RESPONSES,
    BAD_REQUEST_RESPONSE,
    CRUD_RESPONSES,
)
from app.services.timesheet_service import timesheet_service
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

router = APIRouter(responses={**AUTH_RESPONSES})


@router.get(
    "/user/{user_id}/pdf",
    dependencies=[Depends(deps.get_current_manager)],
    responses={**BAD_REQUEST_RESPONSE, **CRUD_RESPONSES},
)
def get_official_timesheet_user_pdf(
        user_id: int,
        db: Annotated[Session, Depends(deps.get_db)],
        month: Annotated[int, Query(ge=1, le=12)],
        year: Annotated[int, Query(ge=2000)],
) -> StreamingResponse:
    timesheet_service.validate_date_not_future(month, year)
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
    responses={**BAD_REQUEST_RESPONSE},
)
def get_official_timesheet_all_pdf(
        db: Annotated[Session, Depends(deps.get_db)],
        month: Annotated[int, Query(ge=1, le=12)],
        year: Annotated[int, Query(ge=2000)],
        employee_ids: Annotated[list[int] | None, Query()] = None,
) -> StreamingResponse:
    timesheet_service.validate_date_not_future(month, year)
    zip_buffer = timesheet_service.generate_all_timesheets_pdf_zip(db, month, year, employee_ids)
    filename = f"espelhos_ponto_lote_{month:02d}_{year}.zip"

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
