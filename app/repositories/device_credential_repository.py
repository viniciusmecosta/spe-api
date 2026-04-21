from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.security import get_api_key_hash
from app.domain.models.device import DeviceCredential
from app.schemas.device import DeviceCredentialCreate, DeviceCredentialUpdate


class DeviceCredentialRepository:
    def create(self, db: Session, obj_in: DeviceCredentialCreate) -> DeviceCredential:
        hashed_key = get_api_key_hash(obj_in.api_key)
        db_obj = DeviceCredential(
            name=obj_in.name,
            key_type=obj_in.key_type,
            api_key_hash=hashed_key,
            is_active=obj_in.is_active
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get(self, db: Session, id: int) -> Optional[DeviceCredential]:
        return db.query(DeviceCredential).filter(DeviceCredential.id == id).first()

    def get_all(self, db: Session) -> List[DeviceCredential]:
        return db.query(DeviceCredential).all()

    def update(self, db: Session, db_obj: DeviceCredential, obj_in: DeviceCredentialUpdate) -> DeviceCredential:
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)

        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, id: int):
        db.query(DeviceCredential).filter(DeviceCredential.id == id).delete()
        db.commit()


device_credential_repository = DeviceCredentialRepository()