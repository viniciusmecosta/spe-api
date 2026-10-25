from typing import Annotated

from fastapi import APIRouter, Depends

from app.features.daily_summaries.daily_summary_reprocess_schemas import (
    DailySummaryReprocessRequest,
)
from app.features.daily_summaries.daily_summary_reprocess_service import (
    DailySummaryReprocessService,
)
from app.features.system.job_schemas import JobAdmissionResponse
from app.features.users.user_models import User
from app.shared import deps

router = APIRouter()


@router.post("/admin/reprocess", response_model=JobAdmissionResponse, response_model_exclude_unset=True)
async def reprocess_daily_summaries(
    request_in: DailySummaryReprocessRequest,
    service: Annotated[DailySummaryReprocessService, Depends()],
    current_user: Annotated[User, Depends(deps.get_current_maintainer)],
) -> dict[str, str]:
    return await service.start(request_in, current_user.id)
