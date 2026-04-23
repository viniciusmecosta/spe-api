from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.core.config import settings
from app.database.base import Base


def get_local_time():
    return datetime.now(ZoneInfo(settings.TIMEZONE))


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String, nullable=False)
    entity = Column(String, nullable=False)
    entity_id = Column(Integer, nullable=True)
    details = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=get_local_time)

    actor_name = Column(String, nullable=True)
    target_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    target_user_name = Column(String, nullable=True)
    justification = Column(String, nullable=True)
    reason = Column(String, nullable=True)
    record_time = Column(DateTime(timezone=True), nullable=True)
    record_type = Column(String, nullable=True)

    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    old_data = Column(JSON, nullable=True)
    new_data = Column(JSON, nullable=True)

    actor = relationship("User", foreign_keys=[actor_id])
    target_user = relationship("User", foreign_keys=[target_user_id])
