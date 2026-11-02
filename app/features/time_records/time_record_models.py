from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import relationship

from app.core.config import settings
from app.database.base import Base
from app.shared.enums import RecordType
from app.shared.hashid_service import hashid_service


def get_local_time():
    return datetime.now(ZoneInfo(settings.TIMEZONE))


class TimeRecord(Base):
    __tablename__ = "time_records"
    __table_args__ = (
        Index('idx_tr_user_date', 'user_id', 'record_datetime'),
        Index('idx_tr_ignored', 'is_ignored'),
    )

    USERS_ID = "users.id"
    SET_NULL_ACTION = "SET NULL"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey(USERS_ID, ondelete="RESTRICT"), nullable=False)
    source_adjustment_id = Column(Integer, ForeignKey("adjustment_requests.id", ondelete="SET NULL"),
                                  nullable=True, unique=True)
    record_type = Column(Enum(RecordType), nullable=False)
    record_datetime = Column(DateTime(timezone=True), nullable=False)
    ip_address = Column(String, nullable=True)
    device_name = Column(String, nullable=True)
    biometric_id = Column(Integer, ForeignKey("user_biometrics.id", ondelete=SET_NULL_ACTION), nullable=True)

    edited_by = Column(Integer, ForeignKey(USERS_ID, ondelete=SET_NULL_ACTION), nullable=True)
    edit_justification = Column(String, nullable=True)

    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by = Column(Integer, ForeignKey(USERS_ID, ondelete=SET_NULL_ACTION), nullable=True)
    is_ignored = Column(Boolean, default=False, nullable=False)
    original_record_id = Column(Integer, ForeignKey("time_records.id", name="fk_time_records_original_record_id",
                                                    ondelete=SET_NULL_ACTION, deferrable=True, initially="DEFERRED"),
                                nullable=True)

    created_at = Column(DateTime(timezone=True), default=get_local_time, nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=get_local_time, nullable=True)

    user = relationship("User", back_populates="time_records", foreign_keys=[user_id])
    editor = relationship("User", foreign_keys=[edited_by])
    deleter = relationship("User", foreign_keys=[deleted_by])
    biometric = relationship("UserBiometric", back_populates="time_records")
    original_record = relationship("TimeRecord", remote_side=[id], backref="edits")

    @property
    def editor_name(self) -> str | None:
        return self.editor.name if self.editor else None

    @property
    def short_id(self) -> str:
        return hashid_service.encode(self.id)
