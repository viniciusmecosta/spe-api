from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.core.config import settings
from app.database.base import Base
from app.shared.enums import DeviceKeyType


def get_local_time():
    return datetime.now(ZoneInfo(settings.TIMEZONE))


class DeviceCredential(Base):
    __tablename__ = "device_credentials"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    key_type = Column(Enum(DeviceKeyType), nullable=False, default=DeviceKeyType.DEVICE)
    api_key_hash = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=get_local_time)
    updated_at = Column(DateTime(timezone=True), default=get_local_time, onupdate=get_local_time)


class Firmware(Base):
    __tablename__ = "firmwares"

    id = Column(Integer, primary_key=True, index=True)
    version = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=get_local_time)


class UserBiometric(Base):
    __tablename__ = "user_biometrics"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    sensor_index = Column(Integer, nullable=True)
    template_data = Column(String, nullable=True)
    finger_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=get_local_time)

    user = relationship("User", back_populates="biometrics")
    time_records = relationship("TimeRecord", back_populates="biometric")
