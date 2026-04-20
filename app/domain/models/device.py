from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum
import pytz

from app.core.config import settings
from app.database.base import Base
from app.domain.models.enums import DeviceKeyType

def get_local_time():
    return datetime.now(pytz.timezone(settings.TIMEZONE))

class DeviceCredential(Base):
    __tablename__ = "device_credentials"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    key_type = Column(Enum(DeviceKeyType), nullable=False, default=DeviceKeyType.DEVICE)
    api_key_hash = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=get_local_time)
    updated_at = Column(DateTime(timezone=True), default=get_local_time, onupdate=get_local_time)