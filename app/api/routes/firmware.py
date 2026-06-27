import os
import shutil

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.api.deps import get_db, get_current_maintainer, verify_device_api_key
from app.core.config import settings
from app.domain.models.firmware import Firmware
from app.schemas.firmware import FirmwareResponse

router = APIRouter()

FIRMWARE_DIR = os.path.join(settings.UPLOAD_DIR, "firmware")
os.makedirs(FIRMWARE_DIR, exist_ok=True)


@router.post("/upload", response_model=FirmwareResponse)
def upload_firmware(
        version: str = Form(...),
        file: UploadFile = File(...),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_maintainer)
):
    if not file.filename.endswith('.bin'):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Apenas arquivos .bin são permitidos")

    existing = db.query(Firmware).filter(Firmware.version == version).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Versão já existe")

    file_path = os.path.join(FIRMWARE_DIR, f"firmware_{version}.bin")

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    firmware = Firmware(version=version, file_path=file_path)
    db.add(firmware)
    db.commit()
    db.refresh(firmware)

    return firmware


@router.get("/check", response_model=FirmwareResponse)
def check_firmware(
        device=Depends(verify_device_api_key),
        db: Session = Depends(get_db)
):
    latest = db.query(Firmware).order_by(desc(Firmware.created_at)).first()
    if not latest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nenhum firmware disponível")

    return latest


@router.get("/download")
def download_firmware(
        version: str,
        device=Depends(verify_device_api_key),
        db: Session = Depends(get_db)
):
    firmware = db.query(Firmware).filter(Firmware.version == version).first()

    if not firmware or not os.path.exists(firmware.file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Firmware não encontrado")

    return FileResponse(
        path=firmware.file_path,
        media_type="application/octet-stream",
        filename=f"firmware_{version}.bin"
    )