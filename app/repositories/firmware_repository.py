from typing import Optional
from sqlalchemy import desc
from sqlalchemy.orm import Session
from app.domain.models.firmware import Firmware

class FirmwareRepository:
    def get_by_version(self, db: Session, version: str) -> Optional[Firmware]:
        return db.query(Firmware).filter(Firmware.version == version).first()

    def get_latest(self, db: Session) -> Optional[Firmware]:
        return db.query(Firmware).order_by(desc(Firmware.created_at)).first()

    def create(self, db: Session, version: str, file_path: str) -> Firmware:
        db_obj = Firmware(version=version, file_path=file_path)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

firmware_repository = FirmwareRepository()