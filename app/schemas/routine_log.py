from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class RoutineLogBase(BaseModel):
    routine_type: str
    status: str
    target_date: date | None = None
    details: str | None = None


class RoutineLogCreate(RoutineLogBase):
    pass


class RoutineLogResponse(RoutineLogBase):
    id: int
    execution_time: datetime

    model_config = ConfigDict(from_attributes=True)
