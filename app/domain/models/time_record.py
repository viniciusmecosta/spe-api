from sqlalchemy import Column, Integer, DateTime, ForeignKey, String, Boolean
from sqlalchemy.orm import relationship
from app.database.base import Base


class TimeRecord(Base):
    __tablename__ = "time_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    type = Column(String, nullable=False)  # 'entry' or 'exit'

    biometric_id = Column(Integer, ForeignKey("user_biometrics.id"), nullable=True)

    original_timestamp = Column(DateTime(timezone=True), nullable=True)
    is_manual = Column(Boolean, default=False)
    edited_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    edit_reason = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="time_records", foreign_keys=[user_id])
    editor = relationship("User", foreign_keys=[edited_by])
    biometric = relationship("UserBiometric", back_populates="time_records")