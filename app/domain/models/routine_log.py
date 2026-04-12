from datetime import datetime

import pytz
from sqlalchemy import Column, Integer, String, DateTime, Date

from app.core.config import settings
from app.database.base import Base


def get_local_time():
    tz = pytz.timezone(settings.TIMEZONE)
    return datetime.now(tz).replace(tzinfo=None)

class RoutineLog(Base):
    __tablename__ = "routine_logs"

    id = Column(Integer, primary_key=True, index=True)
    routine_type = Column(String, index=True, nullable=False)
    execution_time = Column(DateTime, default=get_local_time, nullable=False)
    target_date = Column(Date, nullable=True)
    status = Column(String, nullable=False)
    details = Column(String, nullable=True)