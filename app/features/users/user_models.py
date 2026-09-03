from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Time,
)
from sqlalchemy.orm import relationship

from app.core.config import settings
from app.database.base import Base
from app.shared.enums import UserRole


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
    is_daily_excess_enabled = Column(Boolean, nullable=True, default=True)

    user = relationship("User", back_populates="historical_schedules")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    name = Column(String)
    email = Column(String, unique=True, index=True, nullable=True)
    cpf = Column(String, unique=True, index=True, nullable=True)
    pis = Column(String, nullable=True)
    endereco = Column(String, nullable=True)
    data_nascimento = Column(Date, nullable=True)
    password_hash = Column(String)
    is_active = Column(Boolean, default=True)
    role = Column(Enum(UserRole, native_enum=False, length=50), default=UserRole.EMPLOYEE)
    can_manual_punch_desktop = Column(Boolean, default=True)
    can_manual_punch_mobile = Column(Boolean, default=False)
    can_export_report = Column(Boolean, default=False)
    is_exempt_from_rules = Column(Boolean, default=False)
    is_tolerance_exempt = Column(Boolean, default=False)
    auto_print_receipt = Column(Boolean, nullable=True)

    created_at = Column(DateTime(timezone=True), default=get_local_time)
    updated_at = Column(DateTime(timezone=True), default=get_local_time, onupdate=get_local_time)

    historical_schedules = relationship("UserWorkScheduleConfig", back_populates="user", cascade="all, delete-orphan")
    time_records = relationship("TimeRecord", back_populates="user", foreign_keys="TimeRecord.user_id")
    biometrics = relationship("UserBiometric", back_populates="user", cascade="all, delete-orphan")

    current_schedules_rel = relationship(
        "UserWorkScheduleConfig",
        primaryjoin="and_(User.id == UserWorkScheduleConfig.user_id, "
                    "UserWorkScheduleConfig.valid_from <= func.date('now', 'localtime'), "
                    "or_(UserWorkScheduleConfig.valid_until.is_(None), UserWorkScheduleConfig.valid_until >= func.date('now', 'localtime')))",
        viewonly=True,
    )

    @property
    def current_schedules(self):
        return self.current_schedules_rel
