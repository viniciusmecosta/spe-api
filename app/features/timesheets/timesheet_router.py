from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.features.timesheets.anomaly_service import AnomalyService
from app.features.timesheets.timesheet_schemas import AnomalyResponse
from app.features.timesheets.timesheet_service import TimesheetService
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
async def get_official_timesheet_user_pdf(
        user_id: int,
        month: Annotated[int, Query(ge=1, le=12)],
        year: Annotated[int, Query(ge=2000)],
        service: Annotated[TimesheetService, Depends()],
) -> StreamingResponse:
    service.validate_date_not_future(month, year)
    pdf_buffer = await service.generate_user_timesheet_pdf(user_id=user_id, month=month, year=year)
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
async def get_official_timesheet_all_pdf(
        month: Annotated[int, Query(ge=1, le=12)],
        year: Annotated[int, Query(ge=2000)],
        service: Annotated[TimesheetService, Depends()],
        employee_ids: Annotated[list[int] | None, Query()] = None,
) -> StreamingResponse:
    service.validate_date_not_future(month, year)
    zip_buffer = await service.generate_all_timesheets_pdf_zip(month=month, year=year, employee_ids=employee_ids)
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
async def get_all_anomalies(
        month: int,
        year: int,
        service: Annotated[AnomalyService, Depends()],
) -> list[AnomalyResponse]:
    return await service.get_anomalies_by_month(month=month, year=year)


@anomalies_router.get(
    "/user/{user_id}",
    dependencies=[Depends(deps.get_current_manager)],
)
async def get_user_anomalies(
        user_id: int,
        month: int,
        year: int,
        service: Annotated[AnomalyService, Depends()],
) -> list[AnomalyResponse]:
    return await service.get_anomalies_by_month(month=month, year=year, user_id=user_id)
