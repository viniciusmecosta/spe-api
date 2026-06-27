import os
import shutil
from fastapi import UploadFile, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.models.firmware import Firmware
from app.repositories.firmware_repository import firmware_repository
from app.services.audit_service import audit_service


class FirmwareService:
    def __init__(self):
        self.firmware_dir = os.path.join(settings.UPLOAD_DIR, "firmware")
        os.makedirs(self.firmware_dir, exist_ok=True)

    def upload_firmware(self, db: Session, version: str, file: UploadFile, current_user_id: int) -> Firmware:
        if not file.filename.endswith('.bin'):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Apenas arquivos .bin são permitidos")

        existing = firmware_repository.get_by_version(db, version)
        if existing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Versão já existe")

        file_path = os.path.join(self.firmware_dir, f"firmware_{version}.bin")

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        firmware = firmware_repository.create(db, version=version, file_path=file_path)

        audit_service.log(
            db, actor_id=current_user_id, action="UPLOAD", entity="FIRMWARE", entity_id=firmware.id,
            new_data={"version": version, "file_path": file_path}
        )

        return firmware

    def get_latest_firmware(self, db: Session) -> Firmware:
        latest = firmware_repository.get_latest(db)
        if not latest:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nenhum firmware disponível")
        return latest

    def get_firmware_file(self, db: Session, version: str) -> str:
        firmware = firmware_repository.get_by_version(db, version)
        if not firmware or not os.path.exists(firmware.file_path):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Firmware não encontrado")
        return firmware.file_path


firmware_service = FirmwareService()