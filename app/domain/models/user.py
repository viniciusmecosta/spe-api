from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Time,
)
from sqlalchemy.orm import relationship

from app.core.config import settings
from app.database.base import Base


def get_local_time():
    return datetime.now(ZoneInfo(settings.TIMEZONE))


class UserWorkScheduleConfig(Base):
    __tablename__ = "user_work_schedule_configs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    day_of_week = Column(Integer, nullable=False)
    daily_hours = Column(Float, nullable=False)
    entry_1 = Column(Time, nullable=True)
    exit_1 = Column(Time, nullable=True)
    entry_2 = Column(Time, nullable=True)
    exit_2 = Column(Time, nullable=True)
    valid_from = Column(Date, nullable=False)
    valid_until = Column(Date, nullable=True)

    user = relationship("User", back_populates="historical_schedules")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True, nullable=True)
    cpf = Column(String, unique=True, index=True, nullable=True)
    pis = Column(String, nullable=True)
    endereco = Column(String, nullable=True)
    data_nascimento = Column(Date, nullable=True)
    password_hash = Column(String)
    is_active = Column(Boolean, default=True)
    role = Column(String, default="EMPLOYEE")
    can_manual_punch_desktop = Column(Boolean, default=True)
    can_manual_punch_mobile = Column(Boolean, default=False)
    can_export_report = Column(Boolean, default=False)
    is_exempt_from_rules = Column(Boolean, default=False)
    is_tolerance_exempt = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), default=get_local_time)
    updated_at = Column(DateTime(timezone=True), default=get_local_time, onupdate=get_local_time)

    historical_schedules = relationship("UserWorkScheduleConfig", back_populates="user", cascade="all, delete-orphan", lazy="selectin")
    time_records = relationship("TimeRecord", back_populates="user", foreign_keys="TimeRecord.user_id")
    biometrics = relationship("UserBiometric", back_populates="user", cascade="all, delete-orphan", lazy="selectin")
    
    @property
    def current_schedules(self):
        from datetime import date
        today = date.today()
        return [
            sch for sch in self.historical_schedules 
            if sch.valid_from <= today and (sch.valid_until is None or sch.valid_until >= today)
        ]
