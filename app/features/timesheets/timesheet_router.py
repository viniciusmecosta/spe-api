from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.features.timesheets.anomaly_service import anomaly_service
from app.features.timesheets.timesheet_schemas import AnomalyResponse
from app.features.timesheets.timesheet_service import timesheet_service
from app.shared import deps
from app.shared.openapi_responses import (
    AUTH_RESPONSES,
    BAD_REQUEST_RESPONSE,
    CRUD_RESPONSES,
)

router = APIRouter(responses={**AUTH_RESPONSES})
anomalies_router = APIRouter(responses={**AUTH_RESPONSES})


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


@anomalies_router.get(
    "/all",
    dependencies=[Depends(deps.get_current_manager)],
)
def get_all_anomalies(
    month: int,
    year: int,
    db: Annotated[Session, Depends(deps.get_db)],
) -> list[AnomalyResponse]:
    return anomaly_service.get_anomalies_by_month(db, month, year)


@anomalies_router.get(
    "/user/{user_id}",
    dependencies=[Depends(deps.get_current_manager)],
)
def get_user_anomalies(
    user_id: int,
    month: int,
    year: int,
    db: Annotated[Session, Depends(deps.get_db)],
) -> list[AnomalyResponse]:
    return anomaly_service.get_anomalies_by_month(db, month, year, user_id=user_id)
