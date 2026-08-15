import os
import re
import shutil
import time

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import ROOT_DIR, settings
from app.features.devices.device_models import Firmware
from app.features.devices.device_repository import firmware_repository
from app.features.system.audit_service import audit_service


class FirmwareService:
    def __init__(self):
        self.firmware_dir = os.path.join(settings.UPLOAD_DIR, "firmware")
        os.makedirs(self.firmware_dir, exist_ok=True)

    def parse_version(self, version: str) -> tuple[int, int, int]:
        match = re.match(r"^v(\d+)\.(\d+)\.(\d+)$", version)
        if not match:
            raise ValueError("Formato de versão inválido")
        return int(match.group(1)), int(match.group(2)), int(match.group(3))

    def upload_firmware(self, db: Session, version: str, file: UploadFile, current_user_id: int) -> Firmware:
        try:
            new_ver_tuple = self.parse_version(version)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A versão deve estar no formato vx.x.x (ex: v0.3.1)"
            )

        if not file.filename.endswith('.bin'):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Apenas arquivos .bin são permitidos")

        latest = firmware_repository.get_latest(db)
        if latest:
            try:
                latest_ver_tuple = self.parse_version(latest.version)
                if new_ver_tuple <= latest_ver_tuple:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"A nova versão ({version}) deve ser estritamente maior que a versão atual ({latest.version})"
                    )
            except ValueError:
                pass

        existing = firmware_repository.get_by_version(db, version)
        if existing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Versão já existe")

        timestamp = int(time.time())
        absolute_file_path = os.path.join(self.firmware_dir, f"firmware_{version}_{timestamp}.bin")
        relative_file_path = os.path.relpath(absolute_file_path, ROOT_DIR)

        with open(absolute_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        firmware = firmware_repository.create(db, version=version, file_path=relative_file_path)

        audit_service.log(
            db, user_id=current_user_id, action="UPLOAD", entity="FIRMWARE", entity_id=firmware.id,
            new_data={"version": version, "file_path": relative_file_path}
        )

        return firmware

    def update_firmware_file(self, db: Session, version: str, file: UploadFile, current_user_id: int) -> Firmware:
        if not file.filename.endswith('.bin'):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Apenas arquivos .bin são permitidos")

        firmware_old = firmware_repository.get_by_version(db, version)
        if not firmware_old:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Firmware não encontrado")

        timestamp = int(time.time())
        absolute_file_path = os.path.join(self.firmware_dir, f"firmware_{version}_{timestamp}.bin")
        relative_file_path = os.path.relpath(absolute_file_path, ROOT_DIR)

        with open(absolute_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        firmware = firmware_repository.create(db, version=version, file_path=relative_file_path)

        old_data = {"file_path": firmware_old.file_path}
        new_data_raw = {"file_path": relative_file_path}
        
        actual_old, actual_new = audit_service.compute_diffs(old_data, new_data_raw)

        audit_service.log(
            db, user_id=current_user_id, action="UPDATE", entity="FIRMWARE", entity_id=firmware.id,
            old_data=actual_old, new_data=actual_new
        )

        return firmware

    def get_latest_firmware(self, db: Session) -> Firmware:
        latest = firmware_repository.get_latest(db)
        if not latest:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nenhum firmware disponível")
        return latest

    def get_all_firmwares(self, db: Session) -> list[Firmware]:
        return firmware_repository.get_all(db)

    def get_firmware_file(self, db: Session, version: str) -> str:
        firmware = firmware_repository.get_by_version(db, version)
        if not firmware:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Firmware não encontrado")

        absolute_file_path = os.path.join(ROOT_DIR, firmware.file_path) if not os.path.isabs(
            firmware.file_path) else firmware.file_path
        if not os.path.exists(absolute_file_path):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="Arquivo do firmware não encontrado no servidor")

        return absolute_file_path


firmware_service = FirmwareService()
