from datetime import date
from pydantic import BaseModel, ConfigDict


class HolidayBase(BaseModel):
    date: date
    name: str


class HolidayCreate(HolidayBase):
    pass


class HolidayResponse(HolidayBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
