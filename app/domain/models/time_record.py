from sqlalchemy import Column, Integer, DateTime, ForeignKey, String, Boolean, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.base import Base
from app.domain.models.enums import RecordType


class TimeRecord(Base):
    __tablename__ = "time_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    record_type = Column(Enum(RecordType), nullable=False)
    record_datetime = Column(DateTime(timezone=True), nullable=False)
    ip_address = Column(String, nullable=True)
    is_time_verified = Column(Boolean, default=False)

    biometric_id = Column(Integer, ForeignKey("user_biometrics.id"), nullable=True)

    original_timestamp = Column(DateTime(timezone=True), nullable=True)
    is_manual = Column(Boolean, default=False)
    edited_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    edit_reason = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="time_records", foreign_keys=[user_id])
    editor = relationship("User", foreign_keys=[edited_by])
    biometric = relationship("UserBiometric", back_populates="time_records")


class ManualAdjustment(Base):
    __tablename__ = "manual_adjustments"

    id = Column(Integer, primary_key=True, index=True)
    time_record_id = Column(Integer, ForeignKey("time_records.id"), nullable=False)
    previous_type = Column(Enum(RecordType), nullable=False)
    new_type = Column(Enum(RecordType), nullable=False)
    adjusted_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    adjusted_at = Column(DateTime(timezone=True), server_default=func.now())

    time_record = relationship("TimeRecord", backref="manual_adjustments")
    adjusted_by = relationship("User", foreign_keys=[adjusted_by_user_id])
