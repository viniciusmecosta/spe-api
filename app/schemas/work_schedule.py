from pydantic import BaseModel, ConfigDict


class WorkScheduleBase(BaseModel):
    day_of_week: int
    daily_hours: float


class WorkScheduleCreate(WorkScheduleBase):
    pass


class WorkSchedule(WorkScheduleBase):
    id: int
    user_id: int

    model_config = ConfigDict(from_attributes=True)
