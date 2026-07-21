from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import time, date


class WorkScheduleBase(BaseModel):
    day_of_week: int
    daily_hours: float
    entry_1: Optional[time] = None
    exit_1: Optional[time] = None
    entry_2: Optional[time] = None
    exit_2: Optional[time] = None
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None


class WorkScheduleCreate(WorkScheduleBase):
    id: Optional[int] = None


class WorkSchedule(WorkScheduleBase):
    id: int
    user_id: int

    model_config = ConfigDict(from_attributes=True)
