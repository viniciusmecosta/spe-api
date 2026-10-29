from datetime import date

from pydantic import BaseModel, ConfigDict

from app.shared.validation import BusinessDate


class HolidayBase(BaseModel):
    date: date
    name: str


class HolidayCreate(HolidayBase):
    date: BusinessDate


class HolidayResponse(HolidayBase):
    id: int

    model_config = ConfigDict(from_attributes=True)

