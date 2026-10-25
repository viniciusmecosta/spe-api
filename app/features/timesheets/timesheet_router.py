from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.features.timesheets.anomaly_service import AnomalyService
from app.features.timesheets.timesheet_schemas import AnomalyResponse
from app.features.timesheets.timesheet_service import TimesheetService, TimesheetZip
from app.shared import deps
from app.shared.enums import UserRole
from app.shared.openapi_responses import (
    AUTH_RESPONSES,
    BAD_REQUEST_RESPONSE,
    CRUD_RESPONSES,
)
from app.shared.validation import Month, Year

router = APIRouter(responses={**AUTH_RESPONSES})
anomalies_router = APIRouter(responses={**AUTH_RESPONSES})


@router.get(
    "/user/{user_id}/pdf",
    dependencies=[Depends(deps.get_current_manager)],
    responses={**BAD_REQUEST_RESPONSE, **CRUD_RESPONSES},
)
async def get_official_timesheet_user_pdf(
        user_id: int,
        month: Month,
        year: Year,
        service: Annotated[TimesheetService, Depends()],
) -> StreamingResponse:
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
    responses={
        **BAD_REQUEST_RESPONSE,
        200: {
            "description": "ZIP dos espelhos; exportações parciais incluem manifesto_exportacao.json.",
            "headers": {
                "X-Export-Status": {"schema": {"type": "string", "enum": ["complete", "partial"]}},
                "X-Export-Generated-Count": {"schema": {"type": "integer"}},
                "X-Export-Failed-Count": {"schema": {"type": "integer"}},
            },
        },
        503: {"description": "Nenhum espelho pôde ser gerado; tente novamente."},
    },
)
async def get_official_timesheet_all_pdf(
        month: Month,
        year: Year,
        service: Annotated[TimesheetService, Depends()],
        employee_ids: Annotated[list[int] | None, Depends(deps.parse_optional_employee_ids)] = None,
) -> StreamingResponse:
    zip_buffer = await service.generate_all_timesheets_pdf_zip(month=month, year=year, employee_ids=employee_ids)
    filename = f"espelhos_ponto_lote_{month:02d}_{year}.zip"

    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    if isinstance(zip_buffer, TimesheetZip):
        headers.update(zip_buffer.export_headers)
    return StreamingResponse(zip_buffer, media_type="application/zip", headers=headers)


@anomalies_router.get(
    "/all",
    dependencies=[Depends(deps.get_current_manager)],
)
async def get_all_anomalies(
        month: Month,
        year: Year,
        service: Annotated[AnomalyService, Depends()],
) -> list[AnomalyResponse]:
    return await service.get_anomalies_by_month(month=month, year=year, viewer_role=UserRole.MANAGER)


@anomalies_router.get(
    "/user/{user_id}",
    dependencies=[Depends(deps.get_current_manager)],
)
async def get_user_anomalies(
        user_id: int,
        month: Month,
        year: Year,
        service: Annotated[AnomalyService, Depends()],
) -> list[AnomalyResponse]:
    return await service.get_anomalies_by_month(month=month, year=year, user_id=user_id, viewer_role=UserRole.MANAGER)
