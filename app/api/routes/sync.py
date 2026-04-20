from fastapi import APIRouter, Depends, UploadFile, File

from app.api import deps
from app.domain.models.device import DeviceCredential
from app.services.sync_service import sync_service

router = APIRouter()


@router.post("/database")
def sync_database(
        file: UploadFile = File(...),
        consumer: DeviceCredential = Depends(deps.verify_consumer_api_key)
):
    sync_service.receive_database(file)
    return {"status": "success"}
