from sqlalchemy import Column, Integer, String, Date, Time, Enum, ForeignKey, DateTime, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.base import Base
from app.domain.models.enums import AdjustmentType, AdjustmentStatus


class AdjustmentRequest(Base):
    __tablename__ = "adjustment_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    adjustment_type = Column(Enum(AdjustmentType), nullable=False)
    target_date = Column(Date, nullable=False)
    entry_time = Column(Time, nullable=True)
    exit_time = Column(Time, nullable=True)
    reason_text = Column(String, nullable=True)
    # Novo campo para definir quantidade de horas abonadas
    amount_hours = Column(Float, nullable=True)

    status = Column(Enum(AdjustmentStatus), default=AdjustmentStatus.PENDING, nullable=False)
    manager_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    manager_comment = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", foreign_keys=[user_id], backref="adjustment_requests")
    manager = relationship("User", foreign_keys=[manager_id], backref="reviewed_adjustments")

    @property
    def user_name(self):
        return self.user.name if self.user else "Desconhecido"


class AdjustmentAttachment(Base):
    __tablename__ = "adjustment_attachments"

    id = Column(Integer, primary_key=True, index=True)
    adjustment_request_id = Column(Integer, ForeignKey("adjustment_requests.id"), nullable=False)
    file_path = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    request = relationship("AdjustmentRequest", backref="attachments")
