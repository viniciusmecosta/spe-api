import pytz
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Float
from sqlalchemy.orm import relationship

from app.core.config import settings
from app.database.base import Base


def get_local_time():
    return datetime.now(pytz.timezone(settings.TIMEZONE))


class WorkSchedule(Base):
    __tablename__ = "work_schedules"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    day_of_week = Column(Integer, nullable=False)
    daily_hours = Column(Float, nullable=False)

    user = relationship("User", back_populates="schedules")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, index=True)
    password_hash = Column(String)
    is_active = Column(Boolean, default=True)
    role = Column(String, default="EMPLOYEE")
    can_manual_punch_desktop = Column(Boolean, default=True)
    can_manual_punch_mobile = Column(Boolean, default=False)
    can_export_report = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), default=get_local_time)
    updated_at = Column(DateTime(timezone=True), default=get_local_time, onupdate=get_local_time)

    schedules = relationship("WorkSchedule", back_populates="user", cascade="all, delete-orphan", lazy="joined")
    time_records = relationship("TimeRecord", back_populates="user", foreign_keys="TimeRecord.user_id")
    biometrics = relationship("UserBiometric", back_populates="user", cascade="all, delete-orphan", lazy="joined")
