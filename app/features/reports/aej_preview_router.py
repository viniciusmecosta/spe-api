from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.features.reports.aej_preview_service import AejPreviewService
from app.features.users.user_models import User
from app.shared import deps
from app.shared.validation import Month, Year

router = APIRouter()


@router.get("/aej-preview")
async def export_aej_preview(
    month: Month,
    year: Year,
    user_id: Annotated[int, Query(gt=0)],
    service: Annotated[AejPreviewService, Depends()],
    current_user: Annotated[User, Depends(deps.get_current_maintainer)],
) -> Response:
    return await service.export(user_id, month, year)
