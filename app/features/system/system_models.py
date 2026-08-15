from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import JSON, Column, Date, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship

from app.core.config import settings
from app.database.base import Base


def get_local_time():
    return datetime.now(ZoneInfo(settings.TIMEZONE))


def get_local_time_naive():
    tz = ZoneInfo(settings.TIMEZONE)
    return datetime.now(tz).replace(tzinfo=None)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index('idx_audit_user_action', 'user_id', 'action'),
        Index('idx_audit_entity_time', 'entity', 'entity_id', 'timestamp'),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String, nullable=False)
    entity = Column(String, nullable=False)
    entity_id = Column(Integer, nullable=True)
    old_data = Column(JSON, nullable=True)
    new_data = Column(JSON, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=get_local_time)

    user = relationship("User", foreign_keys=[user_id])


class RoutineLog(Base):
    __tablename__ = "routine_logs"

    id = Column(Integer, primary_key=True, index=True)
    routine_type = Column(String, index=True, nullable=False)
    execution_time = Column(DateTime, default=get_local_time_naive, nullable=False)
    target_date = Column(Date, nullable=True)
    status = Column(String, nullable=False)
    details = Column(String, nullable=True)
