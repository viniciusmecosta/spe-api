from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class RoutineLogBase(BaseModel):
    routine_type: str
    status: str
    target_date: Optional[date] = None
    details: Optional[str] = None


class RoutineLogCreate(RoutineLogBase):
    pass


class RoutineLogResponse(RoutineLogBase):
    id: int
    execution_time: datetime

    model_config = ConfigDict(from_attributes=True)
