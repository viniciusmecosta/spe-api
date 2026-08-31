import os
import re
import shutil
import time
from typing import Annotated

from fastapi import Depends, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import ROOT_DIR, settings
from app.database.session import get_async_db
from app.features.devices.device_exceptions import (
    FirmwareFileNotFoundError,
    FirmwareNotFoundError,
    FirmwareVersionAlreadyExistsError,
    FirmwareVersionNotGreaterError,
    InvalidFirmwareFileTypeError,
    InvalidFirmwareVersionError,
    NoFirmwareAvailableError,
)
from app.features.devices.device_models import Firmware
from app.features.devices.device_repository import AsyncFirmwareRepository, async_firmware_repository
from app.features.system.audit_service import audit_service


class FirmwareService:
    def __init__(
        self,
            db: Annotated[AsyncSession, Depends(get_async_db)] = None,
            repo: Annotated[AsyncFirmwareRepository, Depends()] = None,
    ):
        self.db = db
        self._repo = repo
        self.firmware_dir = os.path.join(settings.UPLOAD_DIR, "firmware")
        os.makedirs(self.firmware_dir, exist_ok=True)

    @property
    def repo(self) -> AsyncFirmwareRepository:
        return self._repo if self._repo is not None else async_firmware_repository

    @repo.setter
    def repo(self, value: AsyncFirmwareRepository) -> None:
        self._repo = value

    def parse_version(self, version: str) -> tuple[int, int, int]:
        match = re.match(r"^v(\d+)\.(\d+)\.(\d+)$", version)
        if not match:
            raise ValueError("Formato de versão inválido")
        return int(match.group(1)), int(match.group(2)), int(match.group(3))

    async def upload_firmware(self, db: AsyncSession | None = None, version: str = "", file: UploadFile | None = None,
                              current_user_id: int = 0) -> Firmware:
        session = db if db is not None else self.db
        assert session is not None
        assert file is not None
        try:
            new_ver_tuple = self.parse_version(version)
        except ValueError:
            raise InvalidFirmwareVersionError()

        if not file.filename or not file.filename.endswith('.bin'):
            raise InvalidFirmwareFileTypeError()

        latest = await self.repo.get_latest(session)
        if latest:
            try:
                latest_ver_tuple = self.parse_version(latest.version)
                if new_ver_tuple <= latest_ver_tuple:
                    raise FirmwareVersionNotGreaterError(
                        f"A nova versão ({version}) deve ser estritamente maior que a versão atual ({latest.version})"
                    )
            except ValueError:
                pass

        existing = await self.repo.get_by_version(session, version)
        if existing:
            raise FirmwareVersionAlreadyExistsError()

        timestamp = int(time.time())
        absolute_file_path = os.path.join(self.firmware_dir, f"firmware_{version}_{timestamp}.bin")
        relative_file_path = os.path.relpath(absolute_file_path, ROOT_DIR)

        with open(absolute_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        firmware = await self.repo.create(session, version=version, file_path=relative_file_path)
        await audit_service.async_log_change(session, current_user_id, "UPLOAD", new_model=firmware)
        return firmware

    async def update_firmware_file(self, db: AsyncSession | None = None, version: str = "",
                                   file: UploadFile | None = None, current_user_id: int = 0) -> Firmware:
        session = db if db is not None else self.db
        assert session is not None
        assert file is not None
        if not file.filename or not file.filename.endswith('.bin'):
            raise InvalidFirmwareFileTypeError()

        firmware_old = await self.repo.get_by_version(session, version)
        if not firmware_old:
            raise FirmwareNotFoundError(version=version)

        timestamp = int(time.time())
        absolute_file_path = os.path.join(self.firmware_dir, f"firmware_{version}_{timestamp}.bin")
        relative_file_path = os.path.relpath(absolute_file_path, ROOT_DIR)

        with open(absolute_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        firmware = await self.repo.create(session, version=version, file_path=relative_file_path)
        await audit_service.async_log_change(session, current_user_id, "UPDATE", old_model=firmware_old,
                                             new_model=firmware)
        return firmware

    async def get_latest_firmware(self, db: AsyncSession | None = None) -> Firmware:
        session = db if db is not None else self.db
        assert session is not None
        latest = await self.repo.get_latest(session)
        if not latest:
            raise NoFirmwareAvailableError()
        return latest

    async def get_all_firmwares(self, db: AsyncSession | None = None) -> list[Firmware]:
        session = db if db is not None else self.db
        assert session is not None
        return await self.repo.get_all(session)

    async def get_firmware_file(self, db: AsyncSession | None = None, version: str = "") -> str:
        session = db if db is not None else self.db
        assert session is not None
        firmware = await self.repo.get_by_version(session, version)
        if not firmware:
            raise FirmwareNotFoundError(version=version)

        absolute_file_path = os.path.join(ROOT_DIR, firmware.file_path) if not os.path.isabs(
            firmware.file_path) else firmware.file_path
        if not os.path.exists(absolute_file_path):
            raise FirmwareFileNotFoundError(version=version)

        return absolute_file_path


firmware_service = FirmwareService()
