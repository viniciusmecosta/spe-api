import pytz
from datetime import datetime
from sqlalchemy import Column, Integer, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.config import settings
from app.database.base import Base


def get_local_time():
    return datetime.now(pytz.timezone(settings.TIMEZONE))

class PayrollClosure(Base):
    __tablename__ = "payroll_closures"

    id = Column(Integer, primary_key=True, index=True)
    month = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)
    is_closed = Column(Boolean, default=True, nullable=False)

    closed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    closed_at = Column(DateTime(timezone=True), default=get_local_time)

    closed_by = relationship("User")

    __table_args__ = (
        UniqueConstraint('month', 'year', name='uq_payroll_month_year'),
    )