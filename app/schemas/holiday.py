from datetime import date
from pydantic import BaseModel

class HolidayBase(BaseModel):
    date: date
    name: str

class HolidayCreate(HolidayBase):
    pass

class HolidayResponse(HolidayBase):
    id: int

    class Config:
        from_attributes = True