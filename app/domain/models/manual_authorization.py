from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.database.base import Base

class ManualPunchAuthorization(Base):
    __tablename__ = "manual_punch_authorizations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    authorized_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    valid_from = Column(DateTime, nullable=False)
    valid_until = Column(DateTime, nullable=False)
    reason = Column(String, nullable=False)

    user = relationship("User", foreign_keys=[user_id])
    authorizer = relationship("User", foreign_keys=[authorized_by])