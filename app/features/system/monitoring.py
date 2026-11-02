from typing import Annotated

from fastapi import APIRouter, Depends

from app.features.system.job_schemas import OperationsResponse, ReadinessResponse
from app.features.system.operations_service import OperationsService
from app.shared import deps

router = APIRouter()


@router.get('/ready', tags=['Health'], response_model=ReadinessResponse)
async def readiness(service: Annotated[OperationsService, Depends()]):
    return await service.readiness()


@router.get('/operations', dependencies=[Depends(deps.get_current_maintainer)], tags=['Health'],
            response_model=OperationsResponse)
async def operations(service: Annotated[OperationsService, Depends()]):
    return await service.snapshot()
