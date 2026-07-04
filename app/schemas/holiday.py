from datetime import date, datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, field_validator

from app.core.config import settings


class HolidayBase(BaseModel):
    date: date
    name: str

    @field_validator('date')
    @classmethod
    def validate_date(cls, v: date) -> date:
        tz = ZoneInfo(settings.TIMEZONE)
        if v < datetime.now(tz).date():
            raise ValueError('A data do feriado não pode ser no passado')
        return v


class HolidayCreate(HolidayBase):
    pass


class HolidayResponse(HolidayBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
