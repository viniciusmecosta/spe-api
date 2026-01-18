from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database.base import Base


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

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    schedules = relationship("WorkSchedule", back_populates="user", cascade="all, delete-orphan", lazy="joined")
    time_records = relationship("TimeRecord", back_populates="user", foreign_keys="TimeRecord.user_id")
    biometrics = relationship("UserBiometric", back_populates="user", cascade="all, delete-orphan")