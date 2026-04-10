from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Date

from app.database.base import Base


class RoutineLog(Base):
    __tablename__ = "routine_logs"

    id = Column(Integer, primary_key=True, index=True)
    routine_type = Column(String, index=True, nullable=False)
    execution_time = Column(DateTime, default=datetime.utcnow, nullable=False)
    target_date = Column(Date, nullable=True)
    status = Column(String, nullable=False)
    details = Column(String, nullable=True)
