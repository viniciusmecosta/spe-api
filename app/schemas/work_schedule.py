from pydantic import BaseModel


class WorkScheduleBase(BaseModel):
    day_of_week: int
    daily_hours: float


class WorkScheduleCreate(WorkScheduleBase):
    pass


class WorkSchedule(WorkScheduleBase):
    id: int
    user_id: int

    class Config:
        from_attributes = True
