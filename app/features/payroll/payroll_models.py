from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import relationship

from app.core.config import settings
from app.database.base import Base


def get_local_time():
    return datetime.now(ZoneInfo(settings.TIMEZONE))


class PayrollClosure(Base):
    __tablename__ = "payroll_closures"
    __table_args__ = (
        Index(
            "uq_payroll_closures_active_period", "year", "month", unique=True,
            postgresql_where=text("deleted_at IS NULL AND is_closed = TRUE"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    month = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)
    is_closed = Column(Boolean, default=True, nullable=False)

    closed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    closed_at = Column(DateTime(timezone=True), default=get_local_time)
    report_path = Column(String, nullable=True)

    closed_by = relationship("User", foreign_keys=[closed_by_user_id])

    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    reopen_observation = Column(String, nullable=True)

    deleter = relationship('User', foreign_keys=[deleted_by])
