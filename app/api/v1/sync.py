from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile

from app.api import deps
from app.services.sync_service import sync_service

router = APIRouter()


@router.post(
    "/database",
    dependencies=[Depends(deps.verify_consumer_api_key)],
    responses={
        400: {"description": "Arquivo inválido ou erro no processamento"},
        401: {"description": "Não autorizado"},
    },
)
def sync_database(
    file: Annotated[UploadFile, File(...)],
) -> dict[str, str]:
    sync_service.receive_database(file)
    return {"status": "success"}
