from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile

from app.api import deps
from app.api.openapi_responses import BAD_REQUEST_RESPONSE, UNAUTHORIZED_RESPONSE
from app.services.sync_service import sync_service

router = APIRouter()


@router.post(
    "/database",
    dependencies=[Depends(deps.verify_consumer_api_key)],
    responses={**BAD_REQUEST_RESPONSE, **UNAUTHORIZED_RESPONSE},
)
def sync_database(
    file: Annotated[UploadFile, File(...)],
) -> dict[str, str]:
    sync_service.receive_database(file)
    return {"status": "success"}
