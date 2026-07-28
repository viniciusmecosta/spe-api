from datetime import date, time

from pydantic import BaseModel, ConfigDict


class WorkScheduleBase(BaseModel):
    day_of_week: int
    daily_hours: float
    entry_1: time | None = None
    exit_1: time | None = None
    entry_2: time | None = None
    exit_2: time | None = None
    valid_from: date | None = None
    valid_until: date | None = None


class WorkScheduleCreate(WorkScheduleBase):
    id: int | None = None


class WorkSchedule(WorkScheduleBase):
    id: int
    user_id: int

    model_config = ConfigDict(from_attributes=True)


class UserScheduleInput(BaseModel):
    user_id: int
    schedules: list[WorkScheduleBase]

class BulkWorkScheduleCreate(BaseModel):
    valid_from: date
    valid_until: date
    users: list[UserScheduleInput]


class BulkWorkScheduleResponse(BaseModel):
    valid_from: date
    valid_until: date
    users: list[UserScheduleInput]
