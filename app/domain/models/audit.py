from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func

from app.database.base import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String, nullable=False)
    entity = Column(String, nullable=False)
    entity_id = Column(Integer, nullable=True)
    details = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    actor_name = Column(String, nullable=True)
    target_user_id = Column(Integer, nullable=True)
    target_user_name = Column(String, nullable=True)
    justification = Column(String, nullable=True)
    reason = Column(String, nullable=True)
    record_time = Column(DateTime(timezone=True), nullable=True)
    record_type = Column(String, nullable=True)