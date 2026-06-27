from fastapi import APIRouter, Depends, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_maintainer, verify_device_api_key
from app.schemas.firmware import FirmwareResponse
from app.services.firmware_service import firmware_service

router = APIRouter()

@router.post("/upload", response_model=FirmwareResponse)
def upload_firmware(
        version: str = Form(...),
        file: UploadFile = File(...),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_maintainer)
):
    return firmware_service.upload_firmware(db, version, file, current_user.id)

@router.get("/check", response_model=FirmwareResponse)
def check_firmware(
        device=Depends(verify_device_api_key),
        db: Session = Depends(get_db)
):
    return firmware_service.get_latest_firmware(db)

@router.get("/download")
def download_firmware(
        version: str,
        device=Depends(verify_device_api_key),
        db: Session = Depends(get_db)
):
    file_path = firmware_service.get_firmware_file(db, version)
    return FileResponse(
        path=file_path,
        media_type="application/octet-stream",
        filename=f"firmware_{version}.bin"
    )