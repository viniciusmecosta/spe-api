from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import Column, Integer, DateTime, ForeignKey, String, Enum, Boolean
from sqlalchemy.orm import relationship

from app.core.config import settings
from app.database.base import Base
from app.domain.models.enums import RecordType, EditJustification


def get_local_time():
    return datetime.now(ZoneInfo(settings.TIMEZONE))


class TimeRecord(Base):
    __tablename__ = "time_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    record_type = Column(Enum(RecordType), nullable=False)
    record_datetime = Column(DateTime(timezone=True), nullable=False)
    ip_address = Column(String, nullable=True)
    device_name = Column(String, nullable=True)
    platform = Column(String, nullable=True)

    biometric_id = Column(Integer, ForeignKey("user_biometrics.id"), nullable=True)

    edited_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    edit_justification = Column(Enum(EditJustification), nullable=True)
    edit_reason = Column(String, nullable=True)

    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_ignored = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime(timezone=True), default=get_local_time)
    updated_at = Column(DateTime(timezone=True), default=get_local_time, onupdate=get_local_time)

    user = relationship("User", back_populates="time_records", foreign_keys=[user_id])
    editor = relationship("User", foreign_keys=[edited_by])
    deleter = relationship("User", foreign_keys=[deleted_by])
    biometric = relationship("UserBiometric", back_populates="time_records")

