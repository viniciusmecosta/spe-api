from sqlalchemy import Column, Integer, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database.base import Base


class PayrollClosure(Base):
    __tablename__ = "payroll_closures"

    id = Column(Integer, primary_key=True, index=True)
    month = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)
    is_closed = Column(Boolean, default=True, nullable=False)

    closed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    closed_at = Column(DateTime(timezone=True), server_default=func.now())

    closed_by = relationship("User")

    __table_args__ = (
        UniqueConstraint('month', 'year', name='uq_payroll_month_year'),
    )